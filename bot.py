import os

from telegram import (
    Update,
    ReplyKeyboardMarkup
)

from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
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
        user["step"] = "confirm"

        text_confirm = (
            "🚕 Проверь заказ:\n\n"
            f"Откуда: {user.get('from')}\n"
            f"Куда: {user.get('to')}"
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

            order_text = (
                "🚕 НОВЫЙ ЗАКАЗ\n\n"
                f"👤 User ID: {user_id}\n"
                f"📍 Откуда: {user.get('from')}\n"
                f"🏁 Куда: {user.get('to')}"
            )

            # уведомление админу
            try:
                await context.bot.send_message(
                    chat_id=ADMIN_ID,
                    text=order_text
                )
            except Exception as e:
                print("ADMIN SEND ERROR:", e)

            await update.message.reply_text(
                "Заказ принят 🚕",
                reply_markup=MENU
            )

            print("NEW ORDER:", user)

            user["step"] = None
            return

    # ================= FALLBACK =================

    await update.message.reply_text(
        "Используй меню 👇",
        reply_markup=MENU
    )

# =========================
# MAIN
# =========================

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            router
        )
    )

    print("BOT STARTED")

    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()