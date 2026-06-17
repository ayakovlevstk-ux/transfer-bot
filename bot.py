import os
import asyncio

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
    ContextTypes,
    filters
)

TOKEN = os.getenv("TOKEN")

if not TOKEN:
    raise ValueError("TOKEN не найден")

ADMIN_ID = 8308540295

PAYMENT_BASE_URL = "https://your-payment-link.com/pay?user="

# =========================
# KEYBOARDS
# =========================

MENU = ReplyKeyboardMarkup(
    [
        ["🚕 Заказать трансфер"],
        ["💰 Цены", "📍 Маршруты"],
        ["❓ Помощь"]
    ],
    resize_keyboard=True
)

CONFIRM_KB = ReplyKeyboardMarkup(
    [
        ["✅ Подтвердить", "❌ Отмена"],
        ["⬅️ Назад"]
    ],
    resize_keyboard=True
)

PAYMENT_KB = InlineKeyboardMarkup([
    [
        InlineKeyboardButton(
            "💳 Я оплатил",
            callback_data="paid"
        )
    ]
])

# =========================
# MEMORY
# =========================

users = {}

def get_user(user_id: int):
    if user_id not in users:
        users[user_id] = {
            "step": None,
            "status": None,
            "timer_task": None
        }
    return users[user_id]

# =========================
# START
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.message.from_user.id)
    user["step"] = None

    await update.message.reply_text(
        "Привет! 🚕 Выбери действие:",
        reply_markup=MENU
    )

# =========================
# ROUTER
# =========================

async def router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text
    user = get_user(user_id)

    step = user.get("step")

    # MENU
    if text == "🚕 Заказать трансфер":
        user["step"] = "from"
        await update.message.reply_text("Откуда едем?")
        return

    if text == "💰 Цены":
        await update.message.reply_text("Керкраде → Амстердам = 120€")
        return

    if text == "📍 Маршруты":
        await update.message.reply_text(
            "Керкраде → Амстердам\nКеркраде → Брюссель"
        )
        return

    if text == "❓ Помощь":
        await update.message.reply_text("Напиши маршрут, и я помогу 🚕")
        return

    if text == "⬅️ Назад":
        user["step"] = None
        await update.message.reply_text("Меню:", reply_markup=MENU)
        return

    # FROM
    if step == "from":
        user["from"] = text
        user["step"] = "to"
        await update.message.reply_text("Куда едем?")
        return

    # TO
    if step == "to":
        user["to"] = text
        user["step"] = "date"
        await update.message.reply_text("Введите дату 📅")
        return

    # DATE
    if step == "date":
        user["date"] = text
        user["step"] = "confirm"

        await update.message.reply_text(
            f"🚕 Проверь заказ:\n\n"
            f"📍 Откуда: {user['from']}\n"
            f"🏁 Куда: {user['to']}\n"
            f"📅 Дата: {user['date']}",
            reply_markup=CONFIRM_KB
        )
        return

    # CONFIRM
    if step == "confirm":

        if text == "❌ Отмена":
            user["step"] = None
            user["status"] = "rejected"

            await update.message.reply_text(
                "Заказ отменен ❌",
                reply_markup=MENU
            )
            return

        if text == "✅ Подтвердить":

            user["status"] = "waiting"

            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "✅ Подтвердить",
                        callback_data=f"accept_{user_id}"
                    ),
                    InlineKeyboardButton(
                        "❌ Отклонить",
                        callback_data=f"reject_{user_id}"
                    )
                ]
            ])

            order_text = (
                "🚕 НОВАЯ ЗАЯВКА\n\n"
                f"👤 Клиент: {user_id}\n"
                f"📍 Откуда: {user['from']}\n"
                f"🏁 Куда: {user['to']}\n"
                f"📅 Дата: {user['date']}\n"
                f"📊 Статус: waiting"
            )

            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=order_text,
                reply_markup=keyboard
            )

            await update.message.reply_text(
                "⏳ Заявка отправлена",
                reply_markup=MENU
            )

            user["step"] = None
            return

    await update.message.reply_text("Используй меню 👇", reply_markup=MENU)

# =========================
# CLIENT PAID → RESERVE SEAT
# =========================

if data == "paid":

    client_id = query.from_user.id
    user = get_user(client_id)

    if user["status"] not in ["awaiting_deposit", "price_sent"]:
        await query.message.reply_text("❌ Оплата не ожидается")
        return

    user["status"] = "reserved"

    if user.get("timer_task"):
        user["timer_task"].cancel()
        user["timer_task"] = None

    await context.bot.send_message(
        chat_id=client_id,
        text=(
            "✅ Оплата получена!\n\n"
            "🚕 Ваше место ЗАКРЕПЛЕНО за вами\n"
            "Спасибо за бронь!"
        )
    )

    return


# ================= ACCEPT =================
if data.startswith("accept_"):

    client_id = int(data.split("_")[1])
    user = get_user(client_id)

    user["status"] = "awaiting_deposit"
    context.user_data["price_for"] = client_id

    await context.bot.send_message(
        chat_id=client_id,
        text=(
            "🚕 Рейс подтверждён!\n\n"
            "💳 Для бронирования места необходимо оплатить 50%\n"
            "⚠️ Без оплаты место НЕ закреплено"
        )
    )

    await query.message.reply_text("Ожидание цены (50% предоплата)")
    return


# ================= REJECT =================
if data.startswith("reject_"):

    client_id = int(data.split("_")[1])
    user = get_user(client_id)

    user["status"] = "rejected"

    await context.bot.send_message(
        chat_id=client_id,
        text="❌ Ваш заказ был отклонён"
    )

    await query.message.reply_text("Заявка отклонена ❌")
    return

# =========================
# ADMIN PRICE
# =========================

async def admin_price(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.message.from_user.id != ADMIN_ID:
        return

    if "price_for" not in context.user_data:
        return

    client_id = context.user_data["price_for"]
    price = float(update.message.text)

    deposit = price * 0.5

    user = get_user(client_id)
    user["status"] = "awaiting_deposit"

    payment_link = PAYMENT_BASE_URL + str(client_id) + f"&amount={deposit}"

    await context.bot.send_message(
    chat_id=client_id,
    text=(
        "💳 БРОНИРОВАНИЕ МЕСТА\n\n"
        f"💰 Общая цена: {price}€\n"
        f"💵 Предоплата 50%: {deposit}€\n\n"
        f"🔗 Оплатить: {payment_link}\n\n"
        "⚠️ После оплаты место будет закреплено"
    ),
    reply_markup=PAYMENT_KB
)
    
async def deposit_timer(client_id: int, context: ContextTypes.DEFAULT_TYPE):
    await asyncio.sleep(3600)  # 1 час (можешь поставить 600 для теста)

    user = get_user(client_id)

    # проверяем: человек НЕ оплатил
    if user["status"] == "awaiting_deposit":

        user["status"] = None

        await context.bot.send_message(
            chat_id=client_id,
            text=(
                "⏳ Время оплаты истекло\n\n"
                "❌ Ваша бронь снята\n"
                "Вы можете оформить заказ заново"
            )
        )    

# =========================
# MAIN
# =========================

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))

    app.add_handler(CallbackQueryHandler(callbacks))

    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, admin_price),
        group=0
    )

    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, router),
        group=1
    )

    print("BOT STARTED")

    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()