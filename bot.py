import os
import asyncio
import threading
import secrets
import requests
from datetime import datetime
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

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
SUPABASE_TABLE_NAME = os.getenv("SUPABASE_TABLE_NAME", "orders")
SUPABASE_DRIVERS_TABLE_NAME = os.getenv("SUPABASE_DRIVERS_TABLE_NAME", "drivers")
SUPABASE_ENABLED = bool(SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY and SUPABASE_TABLE_NAME)

PAYMENT_BASE_URL = "https://your-payment-link.com/pay?user="

BASE_CURRENCY = "GEL"

EXCHANGE_RATES = {
    "GEL": 1,
    "USD": 0.37,
    "EUR": 0.32,
    "RUB": 27.4,
}

ROUTE_PRICES_GEL = {
    "Батуми ↔ Сарпи": 35,
    "Батуми ↔ Тбилиси": 250,
    "Батуми ↔ Владикавказ": 350,
}

REQUEST_PRICE_ROUTES = {
    "✍️ Свой маршрут",
}
DISCOUNT_SEATS_FROM = 4
DISCOUNT_PERCENT = 5


# =========================
# HELPERS
# =========================


STATUS_LABELS = {
    "waiting_admin": "⏳ ожидает подтверждения админа",
    "waiting": "⏳ ожидает подтверждения админа",
    "awaiting_deposit": "💳 ожидает предоплату",
    "awaiting_payment": "💳 ожидает предоплату",
    "payment_check": "🔎 оплата на проверке",
    "reserved": "✅ забронирован",
    "driver_assigned": "👨‍✈️ водитель назначен",
    "driver_on_way": "🚗 водитель едет к вам",
    "driver_arrived": "📍 водитель на месте",
    "passenger_picked": "👥 пассажир в машине",
    "in_progress": "🛣 рейс в пути",
    "completed": "🏁 завершён",
    "cancelled": "❌ отменён",
    "rejected": "❌ отклонён",
    "expired": "⏳ бронь истекла",
}


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def status_label(status: str) -> str:
    return STATUS_LABELS.get(status or "", status or "не указан")


def supabase_headers(prefer: str = None) -> dict:
    headers = {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
    }

    if prefer:
        headers["Prefer"] = prefer

    return headers


def supabase_table_url(params: str = "") -> str:
    return f"{SUPABASE_URL}/rest/v1/{SUPABASE_TABLE_NAME}{params}"


def supabase_drivers_url(params: str = "") -> str:
    return f"{SUPABASE_URL}/rest/v1/{SUPABASE_DRIVERS_TABLE_NAME}{params}"


def parse_driver_card_text(text: str) -> dict:
    raw = text.strip()

    if ";" in raw:
        parts = [part.strip() for part in raw.split(";") if part.strip()]
    else:
        parts = [line.strip() for line in raw.splitlines() if line.strip()]

    while len(parts) < 5:
        parts.append("")

    name, phone, car_model, car_color, plate = parts[:5]
    notes = "\n".join(parts[5:]).strip()

    if not name:
        name = "Водитель"

    return {
        "name": name,
        "phone": phone,
        "car_model": car_model,
        "car_color": car_color,
        "plate": plate,
        "notes": notes,
        "active": True,
    }


def driver_info_from_card(driver: dict) -> str:
    name = driver.get("name") or "Водитель"
    phone = driver.get("phone") or "телефон уточняется"
    car_model = driver.get("car_model") or "авто уточняется"
    car_color = driver.get("car_color") or ""
    plate = driver.get("plate") or ""
    notes = driver.get("notes") or ""

    car_line = ", ".join(part for part in [car_model, car_color, plate] if part)

    lines = [
        f"👨‍✈️ {name}",
        f"📞 {phone}",
        f"🚘 {car_line}" if car_line else "🚘 Авто уточняется",
    ]

    if notes:
        lines.append(f"ℹ️ {notes}")

    return "\n".join(lines)


def format_driver_card(driver: dict) -> str:
    driver_id = driver.get("id", "—")
    return (
        f"👨‍✈️ Карточка водителя #{driver_id}\n\n"
        f"{driver_info_from_card(driver)}"
    )


def create_driver_card(admin_id: int, text: str):
    if not SUPABASE_ENABLED:
        print("SUPABASE DISABLED: driver not saved", flush=True)
        return None

    payload = parse_driver_card_text(text)
    payload["created_by"] = str(admin_id)
    payload["updated_at"] = now_iso()

    try:
        response = requests.post(
            supabase_drivers_url(),
            headers=supabase_headers("return=representation"),
            json=payload,
            timeout=12,
        )

        if response.status_code >= 400:
            print(f"SUPABASE DRIVER CREATE ERROR {response.status_code}: {response.text}", flush=True)
            return None

        data = response.json()
        if isinstance(data, list) and data:
            return data[0]

        return None

    except Exception as exc:
        print(f"SUPABASE DRIVER CREATE EXCEPTION: {exc}", flush=True)
        return None


def fetch_drivers(limit: int = 20):
    if not SUPABASE_ENABLED:
        return None

    try:
        params = (
            "?active=eq.true"
            "&select=id,name,phone,car_model,car_color,plate,notes,active,created_at,updated_at"
            "&order=created_at.desc"
            f"&limit={limit}"
        )

        response = requests.get(
            supabase_drivers_url(params),
            headers=supabase_headers(),
            timeout=12,
        )

        if response.status_code >= 400:
            print(f"SUPABASE DRIVERS FETCH ERROR {response.status_code}: {response.text}", flush=True)
            return []

        return response.json()

    except Exception as exc:
        print(f"SUPABASE DRIVERS FETCH EXCEPTION: {exc}", flush=True)
        return []


def fetch_driver(driver_id: int):
    if not SUPABASE_ENABLED:
        return None

    try:
        response = requests.get(
            supabase_drivers_url(f"?id=eq.{driver_id}&select=id,name,phone,car_model,car_color,plate,notes,active&limit=1"),
            headers=supabase_headers(),
            timeout=12,
        )

        if response.status_code >= 400:
            print(f"SUPABASE DRIVER FETCH ERROR {response.status_code}: {response.text}", flush=True)
            return None

        data = response.json()
        if data:
            return data[0]

        return None

    except Exception as exc:
        print(f"SUPABASE DRIVER FETCH EXCEPTION: {exc}", flush=True)
        return None


def driver_select_keyboard(client_id: int) -> InlineKeyboardMarkup:
    drivers = fetch_drivers() or []
    rows = []

    for driver in drivers[:10]:
        label = f"👨‍✈️ {driver.get('name', 'Водитель')} — {driver.get('car_model', 'авто')}"
        rows.append(
            [
                InlineKeyboardButton(
                    label[:60],
                    callback_data=f"driver_pick_{client_id}_{driver.get('id')}",
                )
            ]
        )

    rows.append(
        [
            InlineKeyboardButton(
                "➕ Создать водителя",
                callback_data=f"driver_add_for_{client_id}",
            )
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                "✍️ Ввести вручную",
                callback_data=f"driver_manual_{client_id}",
            )
        ]
    )

    return InlineKeyboardMarkup(rows)


async def show_driver_selection(message, client_id: int):
    drivers = fetch_drivers()

    if drivers is None:
        await message.reply_text(
            "❌ База водителей не подключена.\n\n"
            "Проверьте Supabase-переменные в Render."
        )
        return

    if not drivers:
        await message.reply_text(
            "Пока нет карточек водителей.\n\n"
            "Создайте водителя или введите данные вручную.",
            reply_markup=driver_select_keyboard(client_id),
        )
        return

    await message.reply_text(
        "Выберите водителя для рейса или создайте новую карточку:",
        reply_markup=driver_select_keyboard(client_id),
    )


def assign_driver_to_user(user: dict, driver: dict):
    user["driver_id"] = driver.get("id")
    user["driver_name"] = driver.get("name", "")
    user["driver_phone"] = driver.get("phone", "")
    user["driver_info"] = driver_info_from_card(driver)


def safe_float(value):
    if value in ["", None]:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def order_payload(user_id: int, user: dict, status: str = None, notes: str = None) -> dict:
    if status:
        user["status"] = status

    if notes:
        user["notes"] = notes

    payload = {
        "updated_at": now_iso(),
        "order_id": str(user.get("order_id", "")),
        "telegram_id": str(user_id),
        "client_name": str(user.get("client_name", "Клиент")),
        "client_url": str(user.get("client_url", "")),
        "route": str(user.get("route", "")),
        "seats": int(user.get("seats")) if str(user.get("seats", "")).isdigit() else None,
        "from_place": str(user.get("from", "")),
        "to_place": str(user.get("to", "")),
        "trip_date": str(user.get("date", "")),
        "comment": str(user.get("comment", "")),
        "status": str(user.get("status", "")),
        "price_gel": safe_float(user.get("price_gel") or user.get("total_price_gel")),
        "deposit_gel": safe_float(user.get("deposit_gel")),
        "price_usd": safe_float(user.get("price_usd")),
        "price_eur": safe_float(user.get("price_eur")),
        "price_rub": safe_float(user.get("price_rub")),
        "notes": str(user.get("notes", "")),
        "driver_name": str(user.get("driver_name", "")),
        "driver_phone": str(user.get("driver_phone", "")),
        "driver_info": str(user.get("driver_info", "")),
        "driver_id": safe_float(user.get("driver_id")),
        "driver_lat": safe_float(user.get("driver_lat")),
        "driver_lng": safe_float(user.get("driver_lng")),
    }

    if user.get("status") == "completed":
        payload["completed_at"] = now_iso()

    if user.get("status") in ["cancelled", "rejected"]:
        payload["cancelled_at"] = now_iso()

    return {
        key: value
        for key, value in payload.items()
        if value not in [None, ""]
    }


def save_order(user_id: int, user: dict, status: str = None, notes: str = None):
    if not SUPABASE_ENABLED:
        print("SUPABASE DISABLED: order not saved", flush=True)
        return None

    payload = order_payload(user_id, user, status=status, notes=notes)

    if not payload.get("order_id"):
        print("SUPABASE SAVE SKIPPED: no order_id", flush=True)
        return None

    try:
        response = requests.post(
            supabase_table_url("?on_conflict=order_id"),
            headers=supabase_headers("resolution=merge-duplicates,return=representation"),
            json=payload,
            timeout=12,
        )

        if response.status_code >= 400:
            print(f"SUPABASE SAVE ERROR {response.status_code}: {response.text}", flush=True)
            return None

        data = response.json()
        print(
            f"SUPABASE SAVED ORDER {payload.get('order_id')} -> {payload.get('status')}",
            flush=True,
        )
        return data

    except Exception as exc:
        print(f"SUPABASE SAVE EXCEPTION: {exc}", flush=True)
        return None


def fetch_user_orders(user_id: int, limit: int = 10):
    if not SUPABASE_ENABLED:
        return None

    try:
        params = (
            f"?telegram_id=eq.{user_id}"
            "&select=order_id,status,route,seats,from_place,to_place,trip_date,comment,"
            "price_gel,deposit_gel,driver_name,driver_phone,driver_info,driver_id,updated_at,created_at"
            "&order=created_at.desc"
            f"&limit={limit}"
        )

        response = requests.get(
            supabase_table_url(params),
            headers=supabase_headers(),
            timeout=12,
        )

        if response.status_code >= 400:
            print(f"SUPABASE FETCH ERROR {response.status_code}: {response.text}", flush=True)
            return []

        return response.json()

    except Exception as exc:
        print(f"SUPABASE FETCH EXCEPTION: {exc}", flush=True)
        return []


def format_order_card(order: dict) -> str:
    price = order.get("price_gel")
    price_text = f"{price:g} GEL" if isinstance(price, (int, float)) else "по запросу"

    lines = [
        f"🧾 Заказ: {order.get('order_id', '—')}",
        f"📊 Статус: {status_label(order.get('status'))}",
        f"🛣 Направление: {order.get('route', '—')}",
        f"👥 Мест: {order.get('seats', '—')}",
        f"📍 Откуда: {order.get('from_place', '—')}",
        f"🏁 Куда: {order.get('to_place', '—')}",
        f"📅 Дата: {order.get('trip_date', '—')}",
        f"💰 Цена: {price_text}",
    ]

    driver_info = order.get("driver_info")
    if driver_info:
        lines.append(f"🚗 Водитель/машина: {driver_info}")

    return "\n".join(lines)


def format_my_orders(orders: list) -> str:
    if orders is None:
        return (
            "📋 История заказов пока не подключена.\n\n"
            "Нужно задать SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY и SUPABASE_TABLE_NAME в Render."
        )

    if not orders:
        return "📋 У вас пока нет заказов."

    cards = [format_order_card(order) for order in orders]
    return "📋 Ваши заказы:\n\n" + "\n\n────────────\n\n".join(cards)


def status_admin_keyboard(client_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🚗 Выехал", callback_data=f"st_onway_{client_id}"),
                InlineKeyboardButton("📍 На месте", callback_data=f"st_arrived_{client_id}"),
            ],
            [
                InlineKeyboardButton("👥 Клиент сел", callback_data=f"st_picked_{client_id}"),
                InlineKeyboardButton("🛣 В пути", callback_data=f"st_progress_{client_id}"),
            ],
            [
                InlineKeyboardButton("🏁 Завершить", callback_data=f"st_done_{client_id}"),
                InlineKeyboardButton("❌ Отменить", callback_data=f"st_cancel_{client_id}"),
            ],
            [
                InlineKeyboardButton("✉️ Ответить клиенту", callback_data=f"reply_{client_id}"),
            ],
        ]
    )


async def set_trip_status(client_id: int, status: str, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(client_id)
    user["status"] = status

    save_order(
        user_id=client_id,
        user=user,
        status=status,
        notes=f"Статус изменён администратором: {status}",
    )

    client_messages = {
        "driver_on_way": (
            "🚗 Водитель выехал к вам.\n\n"
            f"🚘 Машина и водитель:\n{user.get('driver_info') or 'Информация уточняется'}\n\n"
            "Статус поездки можно смотреть в разделе «📋 Мои заказы»."
        ),
        "driver_arrived": (
            "📍 Водитель на месте.\n\n"
            "Пожалуйста, выходите к машине."
        ),
        "passenger_picked": (
            "👥 Посадка подтверждена.\n\n"
            "Хорошей поездки!"
        ),
        "in_progress": (
            "🛣 Рейс начался.\n\n"
            "Статус поездки можно смотреть в разделе «📋 Мои заказы»."
        ),
        "completed": (
            "🏁 Рейс завершён.\n\n"
            "Спасибо, что выбрали нас!"
        ),
        "cancelled": (
            "❌ Рейс отменён.\n\n"
            "Если это ошибка, свяжитесь с менеджером."
        ),
    }

    await context.bot.send_message(
        chat_id=client_id,
        text=client_messages.get(status, f"📊 Статус заказа обновлён: {status_label(status)}"),
    )



def generate_order_id() -> str:
    for _ in range(30):
        order_id = str(secrets.randbelow(900000) + 100000)

        if order_id not in used_order_ids:
            used_order_ids.add(order_id)
            return order_id

    # Fallback, если вдруг случайно 30 раз подряд попали в уже существующий номер.
    order_id = datetime.now().strftime("%H%M%S")
    used_order_ids.add(order_id)
    return order_id


def get_client_name(tg_user) -> str:
    full_name = " ".join(
        part for part in [
            tg_user.first_name,
            tg_user.last_name,
        ]
        if part
    )

    if tg_user.username:
        return f"{full_name} (@{tg_user.username})" if full_name else f"@{tg_user.username}"

    return full_name or "Клиент"


def get_client_url(tg_user) -> str:
    if tg_user.username:
        return f"https://t.me/{tg_user.username}"

    return f"tg://user?id={tg_user.id}"


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


def format_gel(amount: float) -> str:
    if amount is None:
        return "по запросу"

    if float(amount).is_integer():
        return f"{int(amount)} GEL"

    return f"{amount:.2f} GEL"


def calculate_order_price(route: str, seats: int):
    per_seat = ROUTE_PRICES_GEL.get(route)

    if per_seat is None:
        return {
            "route": route,
            "seats": seats,
            "per_seat": None,
            "subtotal": None,
            "discount_percent": 0,
            "discount_amount": 0,
            "total": None,
        }

    subtotal = per_seat * seats
    discount_percent = DISCOUNT_PERCENT if seats >= DISCOUNT_SEATS_FROM else 0
    discount_amount = round(subtotal * discount_percent / 100, 2)
    total = round(subtotal - discount_amount, 2)

    return {
        "route": route,
        "seats": seats,
        "per_seat": per_seat,
        "subtotal": subtotal,
        "discount_percent": discount_percent,
        "discount_amount": discount_amount,
        "total": total,
    }


def price_summary(price_data: dict) -> str:
    if not price_data or price_data.get("total") is None:
        return "💰 Цена: по запросу"

    lines = [
        f"💰 Цена за 1 место: {format_gel(price_data['per_seat'])}",
        f"👥 Мест: {price_data['seats']}",
        f"🧾 Сумма: {format_gel(price_data['subtotal'])}",
    ]

    if price_data.get("discount_percent"):
        lines.append(
            f"🎁 Скидка {price_data['discount_percent']}%: "
            f"-{format_gel(price_data['discount_amount'])}"
        )

    lines.append(f"✅ Итого: {format_gel(price_data['total'])}")

    return "\n".join(lines)


async def send_price_to_client(client_id: int, context: ContextTypes.DEFAULT_TYPE, price: float):
    deposit = round(price * 0.5, 2)

    user = get_user(client_id)
    user["status"] = "awaiting_deposit"
    user["price_gel"] = price
    user["deposit_gel"] = deposit
    user["price_usd"] = convert_price(price, "USD")
    user["price_eur"] = convert_price(price, "EUR")
    user["price_rub"] = convert_price(price, "RUB")

    save_order(
        user_id=client_id,
        user=user,
        status="awaiting_deposit",
        notes="Цена отправлена клиенту, ожидается предоплата",
    )

    payment_link = PAYMENT_BASE_URL + str(client_id) + f"&amount={deposit}"

    await context.bot.send_message(
        chat_id=client_id,
        text=(
            "💳 БРОНИРОВАНИЕ МЕСТА\n\n"
            f"💰 Общая цена:\n{format_multicurrency(price)}\n\n"
            f"💵 Предоплата 50%:\n{format_multicurrency(deposit)}\n\n"
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

    return deposit


# =========================
# KEYBOARDS
# =========================

MENU = ReplyKeyboardMarkup(
    [
        ["🚕 Заказать трансфер"],
        ["💰 Цены", "📦 Посылка"],
        ["📋 Мои заказы", "❓ Помощь"],
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

COMMENT_KB = ReplyKeyboardMarkup(
    [
        ["Без комментария"],
        ["⬅️ Назад"],
    ],
    resize_keyboard=True,
)

ROUTE_KB = ReplyKeyboardMarkup(
    [
        ["Батуми ↔ Владикавказ"],
        ["Батуми ↔ Тбилиси"],
        ["Батуми ↔ Сарпи"],
        ["✍️ Свой маршрут"],
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
used_order_ids = set()


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
        user["status"] = None
        user["order_id"] = generate_order_id()
        user["client_name"] = get_client_name(update.message.from_user)
        user["client_url"] = get_client_url(update.message.from_user)
        user["comment"] = ""
        user["route"] = ""
        user["price_data"] = None
        user["total_price_gel"] = None

        await update.message.reply_text("Сколько мест необходимо?")
        return

    if text == "💰 Цены":
        await update.message.reply_text(
            "💰 Цены за 1 место:\n\n"
            "Батуми ↔ Владикавказ — 350 GEL\n"
            "Батуми ↔ Тбилиси — 250 GEL\n"
            "Батуми ↔ Сарпи — 35 GEL\n\n"
            "🎁 При заказе от 4 мест — скидка 5%.\n"
            "Цена указана за 1 пассажирское место.\n"
            "Обратное направление считается по тому же тарифу.\n"
            "Если нужного направления нет в списке, выберите «✍️ Свой маршрут» при заказе.\n"
            "Финальная цена зависит от даты, багажа, ожидания и пограничных условий."
        )
        return

    if text == "📦 Посылка":
        user["step"] = "parcel_request"
        user["client_name"] = get_client_name(update.message.from_user)
        user["client_url"] = get_client_url(update.message.from_user)

        await update.message.reply_text(
            "📦 Опишите посылку одним сообщением.\n\n"
            "Напишите:\n"
            "• откуда забрать;\n"
            "• куда доставить;\n"
            "• что за посылка;\n"
            "• примерный размер и вес;\n"
            "• когда нужно передать.\n\n"
            "Я передам заявку менеджеру.",
            reply_markup=CONFIRM_KB,
        )
        return

    if text == "📋 Мои заказы":
        orders = fetch_user_orders(user_id, limit=10)
        await update.message.reply_text(
            format_my_orders(orders),
            reply_markup=MENU,
        )
        return

    if text == "❓ Помощь":
        user["step"] = "support_question"
        user["client_name"] = get_client_name(update.message.from_user)
        user["client_url"] = get_client_url(update.message.from_user)

        await update.message.reply_text(
            "Напишите ваш вопрос одним сообщением.\n"
            "Я передам его менеджеру 🚕\n\n"
            "Чтобы вернуться в меню, нажмите «⬅️ Назад».",
            reply_markup=CONFIRM_KB,
        )
        return

    if text == "⬅️ Назад":
        user["step"] = None
        await update.message.reply_text("Меню:", reply_markup=MENU)
        return

    # PARCEL REQUEST
    if step == "parcel_request":
        parcel_text = text.strip()

        if not parcel_text:
            await update.message.reply_text(
                "Опишите посылку текстом или нажмите «⬅️ Назад»."
            )
            return

        user["parcel_text"] = parcel_text
        user["parcel_status"] = "waiting"

        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "✅ Подтвердить посылку",
                        callback_data=f"parcel_accept_{user_id}",
                    ),
                    InlineKeyboardButton(
                        "❌ Отклонить посылку",
                        callback_data=f"parcel_reject_{user_id}",
                    ),
                ],
                [
                    InlineKeyboardButton(
                        "✉️ Ответить клиенту",
                        callback_data=f"reply_{user_id}",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "👤 Открыть клиента",
                        url=user.get("client_url", f"tg://user?id={user_id}"),
                    )
                ],
            ]
        )

        await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=(
                "📦 ЗАЯВКА НА ПОСЫЛКУ\n\n"
                f"👤 Клиент: {user.get('client_name', 'Клиент')}\n"
                f"🆔 Telegram ID: {user_id}\n"
                f"📊 Статус: waiting\n\n"
                f"📦 Описание:\n{parcel_text}"
            ),
            reply_markup=keyboard,
        )

        user["step"] = None

        await update.message.reply_text(
            "✅ Заявка по посылке отправлена менеджеру.\n"
            "Мы ответим вам в ближайшее время.",
            reply_markup=MENU,
        )
        return


    # SUPPORT QUESTION
    if step == "support_question":
        question_text = text.strip()

        if not question_text:
            await update.message.reply_text(
                "Напишите вопрос текстом или нажмите «⬅️ Назад»."
            )
            return

        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "✉️ Ответить клиенту",
                        callback_data=f"reply_{user_id}",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "👤 Открыть клиента",
                        url=user.get("client_url", f"tg://user?id={user_id}"),
                    )
                ],
            ]
        )

        await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=(
                "❓ ВОПРОС ОТ КЛИЕНТА\n\n"
                f"👤 Клиент: {user.get('client_name', 'Клиент')}\n"
                f"🆔 Telegram ID: {user_id}\n\n"
                f"💬 Вопрос:\n{question_text}"
            ),
            reply_markup=keyboard,
        )

        user["step"] = None

        await update.message.reply_text(
            "✅ Вопрос отправлен менеджеру.\n"
            "Мы ответим вам в ближайшее время.",
            reply_markup=MENU,
        )
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
        user["step"] = "route"

        await update.message.reply_text(
            "Выберите направление:",
            reply_markup=ROUTE_KB,
        )
        return

    # ROUTE
    if step == "route":
        route = text.strip()

        if route == "✍️ Свой маршрут":
            user["step"] = "custom_route"
            await update.message.reply_text(
                "Напишите свой маршрут одним сообщением.\n\n"
                "Например:\n"
                "Батуми → Трабзон\n"
                "Кобулети → Владикавказ\n"
                "Аэропорт Кутаиси → Батуми\n\n"
                "Цена по своему маршруту будет рассчитана менеджером.",
                reply_markup=CONFIRM_KB,
            )
            return

        if route not in ROUTE_PRICES_GEL and route not in REQUEST_PRICE_ROUTES:
            await update.message.reply_text(
                "Выберите направление кнопкой ниже или нажмите «✍️ Свой маршрут».",
                reply_markup=ROUTE_KB,
            )
            return

        user["route"] = route
        price_data = calculate_order_price(route, int(user.get("seats", 1)))
        user["price_data"] = price_data
        user["total_price_gel"] = price_data.get("total")

        await update.message.reply_text(
            f"Направление: {route}\n"
            f"{price_summary(price_data)}\n\n"
            "Теперь уточните, откуда именно забрать пассажиров.\n"
            "Например: Батуми, аэропорт / адрес / отель.",
            reply_markup=CONFIRM_KB,
        )

        user["step"] = "from"
        return

    # CUSTOM ROUTE
    if step == "custom_route":
        custom_route = text.strip()

        if len(custom_route) < 3:
            await update.message.reply_text(
                "Напишите маршрут подробнее. Например: Батуми → Трабзон."
            )
            return

        user["route"] = custom_route
        price_data = calculate_order_price(custom_route, int(user.get("seats", 1)))
        user["price_data"] = price_data
        user["total_price_gel"] = None

        await update.message.reply_text(
            f"Направление: {custom_route}\n"
            f"{price_summary(price_data)}\n\n"
            "Теперь уточните, откуда именно забрать пассажиров.\n"
            "Например: адрес, отель, аэропорт или точка встречи.",
            reply_markup=CONFIRM_KB,
        )

        user["step"] = "from"
        return

    # FROM
    if step == "from":
        user["from"] = text
        user["step"] = "to"
        await update.message.reply_text(
            "Куда едем?\n"
            "Например: Владикавказ / аэропорт / адрес / отель."
        )
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
        user["step"] = "comment"

        await update.message.reply_text(
            "Добавьте комментарий к заказу, если нужно.\n\n"
            "Например: номер рейса, много багажа, детское кресло, животное, "
            "точное время, пожелания по остановкам.\n\n"
            "Если комментария нет — нажмите «Без комментария» или напишите «-».",
            reply_markup=COMMENT_KB,
        )
        return

    # COMMENT
    if step == "comment":
        comment_text = text.strip()

        if comment_text.lower() in ["без комментария", "-", "нет", "не", "no"]:
            comment_text = ""

        user["comment"] = comment_text
        user["step"] = "confirm"

        comment_line = user["comment"] if user["comment"] else "—"

        await update.message.reply_text(
            f"🚕 Проверь заказ:\n\n"
            f"🧾 Заказ: {user.get('order_id', '—')}\n"
            f"🛣 Направление: {user.get('route', '—')}\n"
            f"👥 Мест: {user.get('seats', '—')}\n"
            f"📍 Откуда: {user['from']}\n"
            f"🏁 Куда: {user['to']}\n"
            f"📅 Дата: {user['date']}\n"
            f"💬 Комментарий: {comment_line}\n\n"
            f"{price_summary(user.get('price_data'))}",
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
            user["status"] = "waiting_admin"

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
                    ],
                    [
                        InlineKeyboardButton(
                            "👤 Открыть клиента",
                            url=user.get("client_url", f"tg://user?id={user_id}"),
                        )
                    ],
                ]
            )

            order_text = (
                "🚕 НОВАЯ ЗАЯВКА\n\n"
                f"🧾 Заказ: {user.get('order_id', '—')}\n"
                f"👤 Клиент: {user.get('client_name', 'Клиент')}\n"
                f"🆔 Telegram ID: {user_id}\n"
                f"🛣 Направление: {user.get('route', '—')}\n"
                f"👥 Мест: {user.get('seats', '—')}\n"
                f"📍 Откуда: {user['from']}\n"
                f"🏁 Куда: {user['to']}\n"
                f"📅 Дата: {user['date']}\n"
                f"💬 Комментарий: {user.get('comment') or '—'}\n\n"
                f"{price_summary(user.get('price_data'))}\n\n"
                f"📊 Статус: waiting"
            )

            await context.bot.send_message(
                chat_id=ADMIN_CHAT_ID,
                text=order_text,
                reply_markup=keyboard,
            )

            save_order(
                user_id=user_id,
                user=user,
                status="waiting_admin",
                notes="Клиент подтвердил заявку, ожидается решение админа",
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

    # ADMIN START REPLY TO CLIENT
    if data.startswith("reply_"):
        if query.from_user.id not in ADMIN_IDS:
            await query.message.reply_text("❌ Нет доступа")
            return

        client_id = int(data.replace("reply_", ""))
        user = get_user(client_id)

        context.user_data["reply_to_client"] = client_id

        await query.message.reply_text(
            "✉️ Напишите ответ клиенту следующим сообщением.\n\n"
            f"Клиент: {user.get('client_name', 'Клиент')}\n"
            f"Telegram ID: {client_id}\n\n"
            "Чтобы отменить ответ, напишите: отмена"
        )
        return

    # ADMIN ACCEPT PARCEL REQUEST
    if data.startswith("parcel_accept_"):
        if query.from_user.id not in ADMIN_IDS:
            await query.message.reply_text("❌ Нет доступа")
            return

        client_id = int(data.replace("parcel_accept_", ""))
        user = get_user(client_id)
        user["parcel_status"] = "accepted"

        await context.bot.send_message(
            chat_id=client_id,
            text=(
                "✅ Заявка на посылку подтверждена!\n\n"
                "Менеджер свяжется с вами и уточнит детали доставки."
            ),
        )

        await query.message.edit_text(
            text=(
                "✅ ЗАЯВКА НА ПОСЫЛКУ ПОДТВЕРЖДЕНА\n\n"
                f"👤 Клиент: {user.get('client_name', 'Клиент')}\n"
                f"🆔 Telegram ID: {client_id}\n"
                f"📊 Статус: accepted\n\n"
                f"📦 Описание:\n{user.get('parcel_text', '—')}"
            ),
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "✉️ Ответить клиенту",
                            callback_data=f"reply_{client_id}",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "👤 Открыть клиента",
                            url=user.get("client_url", f"tg://user?id={client_id}"),
                        )
                    ],
                ]
            ),
        )

        return

    # ADMIN REJECT PARCEL REQUEST
    if data.startswith("parcel_reject_"):
        if query.from_user.id not in ADMIN_IDS:
            await query.message.reply_text("❌ Нет доступа")
            return

        client_id = int(data.replace("parcel_reject_", ""))
        user = get_user(client_id)
        user["parcel_status"] = "rejected"

        await context.bot.send_message(
            chat_id=client_id,
            text=(
                "❌ К сожалению, сейчас мы не можем взять эту посылку.\n\n"
                "Вы можете написать менеджеру, если хотите уточнить детали."
            ),
        )

        await query.message.edit_text(
            text=(
                "❌ ЗАЯВКА НА ПОСЫЛКУ ОТКЛОНЕНА\n\n"
                f"👤 Клиент: {user.get('client_name', 'Клиент')}\n"
                f"🆔 Telegram ID: {client_id}\n"
                f"📊 Статус: rejected\n\n"
                f"📦 Описание:\n{user.get('parcel_text', '—')}"
            ),
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "✉️ Ответить клиенту",
                            callback_data=f"reply_{client_id}",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "👤 Открыть клиента",
                            url=user.get("client_url", f"tg://user?id={client_id}"),
                        )
                    ],
                ]
            ),
        )

        return

    # ADMIN START DRIVER SELECTION BEFORE "ON WAY"
    if data.startswith("st_onway_"):
        if query.from_user.id not in ADMIN_IDS:
            await query.message.reply_text("❌ Нет доступа")
            return

        client_id = int(data.replace("st_onway_", ""))
        context.user_data["driver_for_trip"] = client_id

        await show_driver_selection(query.message, client_id)
        return

    # ADMIN CREATE DRIVER CARD
    if data == "driver_add" or data.startswith("driver_add_for_"):
        if query.from_user.id not in ADMIN_IDS:
            await query.message.reply_text("❌ Нет доступа")
            return

        client_id = None
        if data.startswith("driver_add_for_"):
            client_id = int(data.replace("driver_add_for_", ""))

        context.user_data["create_driver_for"] = client_id

        await query.message.reply_text(
            "➕ Создание карточки водителя.\n\n"
            "Напишите данные одним сообщением в 5 строк:\n\n"
            "1) Имя водителя\n"
            "2) Телефон\n"
            "3) Машина\n"
            "4) Цвет\n"
            "5) Номер\n\n"
            "Пример:\n"
            "Георгий\n"
            "+995 555 123 456\n"
            "Toyota Sienna\n"
            "белая\n"
            "ABC-123\n\n"
            "Чтобы отменить, напишите: отмена"
        )
        return

    # ADMIN PICK DRIVER FOR TRIP
    if data.startswith("driver_pick_"):
        if query.from_user.id not in ADMIN_IDS:
            await query.message.reply_text("❌ Нет доступа")
            return

        payload = data.replace("driver_pick_", "")
        client_id_text, driver_id_text = payload.split("_", 1)
        client_id = int(client_id_text)
        driver_id = int(driver_id_text)

        driver = fetch_driver(driver_id)

        if not driver:
            await query.message.reply_text("❌ Водитель не найден.")
            return

        user = get_user(client_id)
        assign_driver_to_user(user, driver)

        await set_trip_status(client_id, "driver_on_way", context)

        await query.message.reply_text(
            "✅ Водитель назначен.\n"
            "Клиенту отправлен статус «водитель выехал».\n\n"
            f"{format_driver_card(driver)}",
            reply_markup=status_admin_keyboard(client_id),
        )
        return

    # ADMIN MANUAL DRIVER INPUT FALLBACK
    if data.startswith("driver_manual_"):
        if query.from_user.id not in ADMIN_IDS:
            await query.message.reply_text("❌ Нет доступа")
            return

        client_id = int(data.replace("driver_manual_", ""))
        context.user_data["driver_info_for"] = client_id

        await query.message.reply_text(
            "✍️ Введите данные водителя и машины вручную.\n\n"
            "Например:\n"
            "Георгий, +995 555 123 456\n"
            "Toyota Sienna, белая, ABC-123\n\n"
            "Чтобы отменить, напишите: отмена"
        )
        return

    # ADMIN UPDATE TRIP STATUS
    status_callbacks = {
        "st_arrived_": "driver_arrived",
        "st_picked_": "passenger_picked",
        "st_progress_": "in_progress",
        "st_done_": "completed",
        "st_cancel_": "cancelled",
    }

    for prefix, new_status in status_callbacks.items():
        if data.startswith(prefix):
            if query.from_user.id not in ADMIN_IDS:
                await query.message.reply_text("❌ Нет доступа")
                return

            client_id = int(data.replace(prefix, ""))
            await set_trip_status(client_id, new_status, context)

            await query.message.edit_text(
                "📊 Статус рейса обновлён.\n\n"
                f"Новый статус: {status_label(new_status)}",
                reply_markup=status_admin_keyboard(client_id),
            )
            return

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

        save_order(
            user_id=client_id,
            user=user,
            status="payment_check",
            notes="Клиент нажал кнопку Я оплатил",
        )

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
                ],
                [
                    InlineKeyboardButton(
                        "👤 Открыть клиента",
                        url=user.get("client_url", f"tg://user?id={client_id}"),
                    )
                ],
            ]
        )

        await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=(
                "💳 КЛИЕНТ НАЖАЛ «Я ОПЛАТИЛ»\n\n"
                f"🧾 Заказ: {user.get('order_id', '—')}\n"
                f"👤 Клиент: {user.get('client_name', 'Клиент')}\n"
                f"🆔 Telegram ID: {client_id}\n"
                f"🛣 Направление: {user.get('route', '—')}\n"
                f"👥 Мест: {user.get('seats', '—')}\n"
                f"📍 Откуда: {user.get('from', '—')}\n"
                f"🏁 Куда: {user.get('to', '—')}\n"
                f"📅 Дата: {user.get('date', '—')}\n"
                f"💬 Комментарий: {user.get('comment') or '—'}\n\n"
                f"{price_summary(user.get('price_data'))}\n\n"
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

        save_order(
            user_id=client_id,
            user=user,
            status="reserved",
            notes="Оплата подтверждена администратором",
        )

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
            "✅ Оплата подтверждена. Место закреплено за клиентом.\n\n"
            "Дальше можно менять статус рейса кнопками ниже.",
            reply_markup=status_admin_keyboard(client_id),
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

        save_order(
            user_id=client_id,
            user=user,
            status="awaiting_deposit",
            notes="Администратор отклонил подтверждение оплаты",
        )

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

        save_order(
            user_id=client_id,
            user=user,
            status="awaiting_deposit",
            notes="Заявка подтверждена администратором",
        )

        await context.bot.send_message(
            chat_id=client_id,
            text=(
                "🚕 Рейс подтверждён!\n\n"
                "💳 Для бронирования места необходимо оплатить 50%\n"
                "⚠️ Без оплаты место НЕ закреплено"
            ),
        )

        auto_price = user.get("total_price_gel")

        if auto_price:
            deposit = await send_price_to_client(client_id, context, auto_price)

            await query.message.reply_text(
                "✅ Заявка подтверждена.\n\n"
                f"Цена рассчитана автоматически: {format_gel(auto_price)}\n"
                f"Предоплата 50%: {format_gel(deposit)}"
            )
            return

        context.user_data["price_for"] = client_id

        await query.message.reply_text(
            "Цена по этому направлению не задана автоматически.\n"
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

        save_order(
            user_id=client_id,
            user=user,
            status="rejected",
            notes="Заявка отклонена администратором",
        )

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
# ADMIN DRIVERS
# =========================

async def drivers_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id not in ADMIN_IDS:
        return

    drivers = fetch_drivers()

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "➕ Добавить водителя",
                    callback_data="driver_add",
                )
            ]
        ]
    )

    if drivers is None:
        await update.message.reply_text(
            "❌ База водителей не подключена.\n\n"
            "Проверьте Supabase-переменные в Render.",
            reply_markup=keyboard,
        )
        return

    if not drivers:
        await update.message.reply_text(
            "👨‍✈️ Карточек водителей пока нет.",
            reply_markup=keyboard,
        )
        return

    cards = [format_driver_card(driver) for driver in drivers]
    await update.message.reply_text(
        "👨‍✈️ Водители:\n\n" + "\n\n────────────\n\n".join(cards),
        reply_markup=keyboard,
    )


# =========================
# ADMIN PRICE
# =========================

async def admin_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id not in ADMIN_IDS:
        return

    if "create_driver_for" in context.user_data:
        client_id = context.user_data["create_driver_for"]
        text = update.message.text.strip()

        if text.lower() in ["отмена", "cancel", "❌ отмена"]:
            context.user_data.pop("create_driver_for", None)
            await update.message.reply_text("Создание карточки водителя отменено.")
            raise ApplicationHandlerStop

        driver = create_driver_card(update.message.from_user.id, text)

        if not driver:
            await update.message.reply_text(
                "❌ Не удалось создать карточку водителя.\n"
                "Проверьте таблицу drivers в Supabase и переменные Render."
            )
            raise ApplicationHandlerStop

        context.user_data.pop("create_driver_for", None)

        if client_id:
            await update.message.reply_text(
                "✅ Карточка водителя создана.\n\n"
                f"{format_driver_card(driver)}",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "✅ Назначить на этот рейс",
                                callback_data=f"driver_pick_{client_id}_{driver.get('id')}",
                            )
                        ]
                    ]
                ),
            )
        else:
            await update.message.reply_text(
                "✅ Карточка водителя создана.\n\n"
                f"{format_driver_card(driver)}"
            )

        raise ApplicationHandlerStop

    if "driver_info_for" in context.user_data:
        client_id = context.user_data["driver_info_for"]
        driver_info = update.message.text.strip()

        if driver_info.lower() in ["отмена", "cancel", "❌ отмена"]:
            context.user_data.pop("driver_info_for", None)
            await update.message.reply_text("Ввод данных водителя отменён.")
            raise ApplicationHandlerStop

        if len(driver_info) < 5:
            await update.message.reply_text(
                "Напишите данные подробнее. Например:\n"
                "Георгий, +995 555 123 456\n"
                "Toyota Sienna, белая, ABC-123"
            )
            raise ApplicationHandlerStop

        user = get_user(client_id)
        user["driver_info"] = driver_info

        await set_trip_status(client_id, "driver_on_way", context)

        context.user_data.pop("driver_info_for", None)

        await update.message.reply_text(
            "✅ Данные водителя сохранены.\n"
            "Клиенту отправлен статус: водитель выехал.",
            reply_markup=status_admin_keyboard(client_id),
        )

        raise ApplicationHandlerStop

    if "reply_to_client" in context.user_data:
        client_id = context.user_data["reply_to_client"]
        answer_text = update.message.text.strip()

        if answer_text.lower() in ["отмена", "cancel", "❌ отмена"]:
            context.user_data.pop("reply_to_client", None)
            await update.message.reply_text("Ответ клиенту отменён.")
            raise ApplicationHandlerStop

        try:
            await context.bot.send_message(
                chat_id=client_id,
                text=(
                    "💬 Ответ менеджера:\n\n"
                    f"{answer_text}"
                ),
            )

            context.user_data.pop("reply_to_client", None)

            await update.message.reply_text(
                "✅ Ответ отправлен клиенту."
            )

        except Exception as exc:
            await update.message.reply_text(
                f"❌ Не удалось отправить ответ клиенту: {exc}"
            )

        raise ApplicationHandlerStop

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
    deposit = await send_price_to_client(client_id, context, price)

    user = get_user(client_id)
    user["price_data"] = {
        "route": user.get("route", ""),
        "seats": user.get("seats", 1),
        "per_seat": None,
        "subtotal": None,
        "discount_percent": 0,
        "discount_amount": 0,
        "total": price,
    }
    user["total_price_gel"] = price

    save_order(
        user_id=client_id,
        user=user,
        status="awaiting_deposit",
        notes="Цена введена вручную администратором",
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
        user["status"] = "expired"
        user["timer_task"] = None

        save_order(
            user_id=client_id,
            user=user,
            status="expired",
            notes="Время оплаты истекло",
        )

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

    if SUPABASE_ENABLED:
        print("SUPABASE ENABLED", flush=True)
    else:
        print("SUPABASE DISABLED: My Orders history will not persist", flush=True)

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("drivers", drivers_command))

    app.add_handler(CallbackQueryHandler(callbacks))

    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, admin_price),
        group=0,
    )

    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, router),
        group=1,
    )

    print("BOT STARTED - DRIVER CARDS VERSION", flush=True)

    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
