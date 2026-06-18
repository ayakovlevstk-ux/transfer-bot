import os
import asyncio
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

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
    ContextTypes,
    ApplicationHandlerStop,
    filters,
)

TOKEN = os.getenv("TOKEN")

if not TOKEN:
    raise ValueError("TOKEN не найден")

ADMIN_IDS = {8308540295}
ADMIN_CHAT_ID = -1003903294475

PAYMENT_BASE_URL = "https://your-payment-link.com/pay?user="
BASE_CURRENCY = "GEL"

EXCHANGE_RATES = {
    "GEL": 1,
    "USD": 0.37,
    "EUR": 0.32,
    "RUB": 27.4,
}


def convert_price(amount_gel: float, currency: str) -> float:
    rate = EXCHANGE_RATES.get(currency, 1)
    return round(amount_gel * rate, 2)


def format_multicurrency(amount_gel: float) -> str:
    usd = convert_price(amount_gel, "USD")
    eur = convert_price(amount_gel, "EUR")
    rub = convert_price(amount_gel, "RUB")

    return (
        f"{amount_gel:.0f} GEL\n"
        f"≈ {usd:.0f} USD\n"
        f"≈ {eur:.0f} EUR\n"
        f"≈ {rub:.0f} RUB"
    )

# =========================
# KEYBOARDS
# =========================

MENU = ReplyKeyboardMarkup(
    [
        ["🚕 Заказать трансфер"],
        ["💰 Цены", "📍 Маршруты"],
        ["❓ Помощь"],
    ],
    resize_keyboard=True,
)

CONFIRM_KB = ReplyKeyboardMarkup(
    [
        ["✅ Подтвердить", "❌ Отмена"],
        ["⬅️ Назад"],
    ],
    resize_keyboard=True,
)

PAYMENT_KB = InlineKeyboardMarkup(
    [
        [
            InlineKeyboardButton(
                "💳 Я оплатил",
                callback_data="paid",
            )
        ]
    ]
)

# =========================
# MEMORY
# =========================

users = {}


def get_user(user_id: int):
    if user_id not in users:
        users[user_id] = {
            "step": None,
            "status": None,
            "timer_task": None,
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
        reply_markup=MENU,
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
        user["step"] = "seats"
        await update.message.reply_text(
            "Сколько мест необходимо?\n\n"
            "Введите число от 1 до 7."
        )
        return

    if text == "💰 Цены":
        await update.message.reply_text("Батуми (Аэропорт) → Батуми - 100 \nБатуми → Тбилиси")
        return

    if text == "📍 Маршруты":
        await update.message.reply_text(
            "Батуми (Аэропорт) → Батуми\nБатуми → Тбилиси"
        )
        return

    if text == "❓ Помощь":
        await update.message.reply_text("Напиши маршрут, и я помогу 🚕")
        return

    if text == "⬅️ Назад":
        user["step"] = None
        await update.message.reply_text("Меню:", reply_markup=MENU)
        return

    # SEATS
    if step == "seats":
        try:
            seats = int(text.strip())
        except ValueError:
            await update.message.reply_text(
                "Введите количество мест числом. Например: 2"
            )
            return

        if seats < 1 or seats > 7:
            await update.message.reply_text(
                "Для Toyota Sienna можно указать от 1 до 7 мест.\n"
                "Введите корректное количество."
            )
            return

        user["seats"] = seats
        user["step"] = "from"
        await update.message.reply_text("Откуда едем?")
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
            f"👥 Мест: {user.get('seats', '—')}\n"
            f"📍 Откуда: {user['from']}\n"
            f"🏁 Куда: {user['to']}\n"
            f"📅 Дата: {user['date']}",
            reply_markup=CONFIRM_KB,
        )
        return

    # CONFIRM
    if step == "confirm":
        if text == "❌ Отмена":
            user["step"] = None
            user["status"] = "rejected"

            await update.message.reply_text(
                "Заказ отменен ❌",
                reply_markup=MENU,
            )
            return

        if text == "✅ Подтвердить":
            user["status"] = "waiting"

            keyboard = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "✅ Подтвердить",
                            callback_data=f"accept_{user_id}",
                        ),
                        InlineKeyboardButton(
                            "❌ Отклонить",
                            callback_data=f"reject_{user_id}",
                        ),
                    ]
                ]
            )

            order_text = (
                "🚕 НОВАЯ ЗАЯВКА\n\n"
                f"👤 Клиент: {user_id}\n"
                f"👥 Мест: {user.get('seats', '—')}\n"
                f"📍 Откуда: {user['from']}\n"
                f"🏁 Куда: {user['to']}\n"
                f"📅 Дата: {user['date']}\n"
                f"📊 Статус: waiting"
            )

            await context.bot.send_message(
                chat_id=ADMIN_CHAT_ID,
                text=order_text,
                reply_markup=keyboard,
            )

            await update.message.reply_text(
                "⏳ Заявка отправлена",
                reply_markup=MENU,
            )

            user["step"] = None
            return

    await update.message.reply_text("Используй меню 👇", reply_markup=MENU)


# =========================
# CALLBACKS
# =========================

async def callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data

    await query.answer()

    # CLIENT PAID → SEND PAYMENT CHECK TO ADMIN
    if data == "paid":
        client_id = query.from_user.id
        user = get_user(client_id)

        if user["status"] not in ["awaiting_deposit", "price_sent", "payment_check"]:
            await query.message.reply_text("❌ Оплата не ожидается")
            return

        if user["status"] == "payment_check":
            await query.message.reply_text(
                "⏳ Заявка на проверку оплаты уже отправлена администратору.\n\n"
                "🚕 Место будет закреплено только после подтверждения."
            )
            return

        user["status"] = "payment_check"

        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "✅ Оплата подтверждена",
                        callback_data=f"confirm_payment_{client_id}",
                    ),
                    InlineKeyboardButton(
                        "❌ Оплаты нет",
                        callback_data=f"reject_payment_{client_id}",
                    ),
                ]
            ]
        )

        await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=(
                "💳 КЛИЕНТ НАЖАЛ «Я ОПЛАТИЛ»\n\n"
                f"👤 Клиент: {client_id}\n"
                f"👥 Мест: {user.get('seats', '—')}\n"
                f"📍 Откуда: {user.get('from', '—')}\n"
                f"🏁 Куда: {user.get('to', '—')}\n"
                f"📅 Дата: {user.get('date', '—')}\n\n"
                "Проверь поступление денег и нажми кнопку ниже."
            ),
            reply_markup=keyboard,
        )

        await query.message.reply_text(
            "⏳ Я отправил заявку администратору на проверку оплаты.\n\n"
            "🚕 Место будет закреплено только после подтверждения администратором."
        )

        return

    # ADMIN CONFIRM PAYMENT
    if data.startswith("confirm_payment_"):
        if query.from_user.id not in ADMIN_IDS:
            await query.message.reply_text("❌ Нет доступа")
            return

        client_id = int(data.replace("confirm_payment_", ""))
        user = get_user(client_id)

        if user["status"] not in ["awaiting_deposit", "price_sent", "payment_check"]:
            await query.message.reply_text("❌ Эта оплата уже не ожидается")
            return

        user["status"] = "reserved"

        if user.get("timer_task"):
            user["timer_task"].cancel()
            user["timer_task"] = None

        await context.bot.send_message(
            chat_id=client_id,
            text=(
                "✅ Оплата подтверждена!\n\n"
                "🚕 Ваше место ЗАКРЕПЛЕНО за вами.\n"
                "Спасибо за бронь!"
            ),
        )

        await query.message.edit_text(
            "✅ Оплата подтверждена. Место закреплено за клиентом."
        )

        return

    # ADMIN REJECT PAYMENT
    if data.startswith("reject_payment_"):
        if query.from_user.id not in ADMIN_IDS:
            await query.message.reply_text("❌ Нет доступа")
            return

        client_id = int(data.replace("reject_payment_", ""))
        user = get_user(client_id)

        if user.get("status") == "reserved":
            await query.message.reply_text("❌ Бронь уже подтверждена")
            return

        user["status"] = "awaiting_deposit"

        await context.bot.send_message(
            chat_id=client_id,
            text=(
                "❌ Оплата пока не подтверждена.\n\n"
                "Проверьте платёж или свяжитесь с администратором.\n"
                "🚕 Место пока НЕ закреплено."
            ),
        )

        await query.message.edit_text(
            "❌ Оплата отклонена. Клиенту отправлено уведомление."
        )

        return

    # ADMIN ACCEPT ORDER
    if data.startswith("accept_"):
        if query.from_user.id not in ADMIN_IDS:
            await query.message.reply_text("❌ Нет доступа")
            return

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
            ),
        )

        await query.message.reply_text(
            "Введите полную стоимость поездки в GEL. Например: 100"
        )

        return

    # ADMIN REJECT ORDER
    if data.startswith("reject_"):
        if query.from_user.id not in ADMIN_IDS:
            await query.message.reply_text("❌ Нет доступа")
            return

        client_id = int(data.split("_")[1])
        user = get_user(client_id)

        user["status"] = "rejected"

        if user.get("timer_task"):
            user["timer_task"].cancel()
            user["timer_task"] = None

        await context.bot.send_message(
            chat_id=client_id,
            text="❌ Ваш заказ был отклонён",
        )

        await query.message.reply_text("Заявка отклонена ❌")
        return


# =========================
# ADMIN PRICE
# =========================

async def admin_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id not in ADMIN_IDS:
        return

    if "price_for" not in context.user_data:
        return

    try:
        price = float(update.message.text.replace(",", "."))
    except ValueError:
        await update.message.reply_text(
            "Введите цену числом. Например: 120 или 120.50"
        )
        raise ApplicationHandlerStop

    client_id = context.user_data["price_for"]
    deposit = round(price * 0.5, 2)

    user = get_user(client_id)
    user["status"] = "awaiting_deposit"

    payment_link = PAYMENT_BASE_URL + str(client_id) + f"&amount={deposit}"

    await context.bot.send_message(
        chat_id=client_id,
        text=(
            "💳 БРОНИРОВАНИЕ МЕСТА\n\n"
            f"💰 Общая цена:\n{format_multicurrency(price)}\n\n"
            f"f"💵 Предоплата 50%:\n{format_multicurrency(deposit)}\n\n"
            f"🔗 Оплатить: {payment_link}\n\n"
            "⚠️ После оплаты место будет закреплено"
        ),
        reply_markup=PAYMENT_KB,
    )

    if user.get("timer_task"):
        user["timer_task"].cancel()

    user["timer_task"] = asyncio.create_task(
        deposit_timer(client_id, context)
    )

    context.user_data.pop("price_for", None)

    await update.message.reply_text(
    f"✅ Цена отправлена клиенту.\n\n"
    f"💵 Предоплата 50%:\n{format_multicurrency(deposit)}"
)

    raise ApplicationHandlerStop


# =========================
# DEPOSIT TIMER
# =========================

async def deposit_timer(client_id: int, context: ContextTypes.DEFAULT_TYPE):
    await asyncio.sleep(3600)  # 1 час, для теста можно поставить 600

    user = get_user(client_id)

    # проверяем: человек НЕ оплатил
    if user["status"] in ["awaiting_deposit", "payment_check"]:
        user["status"] = None
        user["timer_task"] = None

        await context.bot.send_message(
            chat_id=client_id,
            text=(
                "⏳ Время оплаты истекло\n\n"
                "❌ Ваша бронь снята\n"
                "Вы можете оформить заказ заново"
            ),
        )


# =========================
# RENDER HEALTH SERVER
# =========================

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, format, *args):
        return


def run_health_server():
    port = int(os.getenv("PORT", "10000"))

    server = ThreadingHTTPServer(
        ("0.0.0.0", port),
        HealthHandler,
    )

    print(f"HEALTH SERVER STARTED ON PORT {port}", flush=True)
    server.serve_forever()


# =========================
# MAIN
# =========================

def main():
    threading.Thread(
        target=run_health_server,
        daemon=True,
    ).start()

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))

    app.add_handler(CallbackQueryHandler(callbacks))

    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, admin_price),
        group=0,
    )

    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, router),
        group=1,
    )

    print("BOT STARTED - SEATS FLOW VERSION", flush=True)

    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
