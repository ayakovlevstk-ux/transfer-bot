import os

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

# =========================
# MEMORY
# =========================

users = {}

def get_user(user_id: int):
    if user_id not in users:
        users[user_id] = {"step": None}
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

    # ================= MENU =================

    if text == "🚕 Заказать трансфер":
        user["step"] = "from"

        await update.message.reply_text(
            "Откуда едем?"
        )
        return

    if text == "💰 Цены":
        await update.message.reply_text(
            "Керкраде → Амстердам = 120€"
        )
        return

    if text == "📍 Маршруты":
        await update.message.reply_text(
            "Керкраде → Амстердам\n"
            "Керкраде → Брюссель"
        )
        return

    if text == "❓ Помощь":
        await update.message.reply_text(
            "Напиши маршрут, и я помогу 🚕"
        )
        return

    # ================= BACK =================

    if text == "⬅️ Назад":
        user["step"] = None

        await update.message.reply_text(
            "Меню:",
            reply_markup=MENU
        )
        return

    # ================= FROM =================

    if step == "from":
        user["from"] = text
        user["step"] = "to"

        await update.message.reply_text(
            "Куда едем?"
        )
        return

    # ================= TO =================

    if step == "to":
        user["to"] = text
        user["step"] = "date"

        await update.message.reply_text(
            "Введите дату поездки 📅\n\nНапример: 25.06.2026"
        )
        return

    # ================= DATE =================

    if step == "date":
        user["date"] = text
        user["step"] = "confirm"

        text_confirm = (
            "🚕 Проверь заказ:\n\n"
            f"📍 Откуда: {user.get('from')}\n"
            f"🏁 Куда: {user.get('to')}\n"
            f"📅 Дата: {user.get('date')}"
        )

        await update.message.reply_text(
            text_confirm,
            reply_markup=CONFIRM_KB
        )
        return

    # ================= CONFIRM =================

    if step == "confirm":

        if text == "❌ Отмена":
            user["step"] = None

            await update.message.reply_text(
                "Заказ отменен ❌",
                reply_markup=MENU
            )
            return

        if text == "✅ Подтвердить":

            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "✅ Подтвердить рейс",
                        callback_data=f"accept_{user_id}"
                    )
                ]
            ])

            order_text = (
                "🚕 НОВАЯ ЗАЯВКА\n\n"
                f"👤 Клиент: {user_id}\n"
                f"📍 Откуда: {user.get('from')}\n"
                f"🏁 Куда: {user.get('to')}\n"
                f"📅 Дата: {user.get('date')}"
            )

            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=order_text,
                reply_markup=keyboard
            )

            await update.message.reply_text(
                "⏳ Заявка отправлена.\nОжидайте подтверждения рейса.",
                reply_markup=MENU
            )

            user["step"] = None
            return

    # ================= FALLBACK =================

    await update.message.reply_text(
        "Используй меню 👇",
        reply_markup=MENU
    )

    # =========================
    # CALLBACKS
    # =========================
async def callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data

    if data.startswith("accept_"):

        client_id = int(data.split("_")[1])

        context.user_data["price_for"] = client_id

        await query.message.reply_text(
            "Введите цену для клиента 💰"
        )

   # =========================
   # ADMIN PRICE
   # =========================

async def admin_price(update: Update, context: ContextTypes.DEFAULT_TYPE):

    # только админ
    if update.message.from_user.id != ADMIN_ID:
        return

    # если бот не ждет цену
    if "price_for" not in context.user_data:
        return

    client_id = context.user_data["price_for"]

    price = update.message.text

    await context.bot.send_message(
        chat_id=client_id,
        text=(
            "✅ Ваш рейс подтвержден!\n\n"
            f"💰 Стоимость поездки: {price}"
        )
    )

    await update.message.reply_text(
        "Цена отправлена клиенту ✅"
    )

    del context.user_data["price_for"]

# =========================
# MAIN
# =========================

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))

    # callback кнопки
    app.add_handler(CallbackQueryHandler(callbacks))

    # админ вводит цену
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            admin_price
        ),
        group=0
    )

    # основной router
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            router
        ),
        group=1
    )

    print("BOT STARTED")

    app.run_polling(drop_pending_updates=True)
if __name__ == "__main__":
    main()