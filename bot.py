import os
import asyncio
import threading
import secrets
import requests
import html
from urllib.parse import urlparse, parse_qs
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
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

ADMIN_IDS = {8308540295, 1688218714}
ADMIN_CHAT_ID = -1003903294475

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
SUPABASE_TABLE_NAME = os.getenv("SUPABASE_TABLE_NAME", "orders")
SUPABASE_DRIVERS_TABLE_NAME = os.getenv("SUPABASE_DRIVERS_TABLE_NAME", "drivers")
SUPABASE_REVIEWS_TABLE_NAME = os.getenv("SUPABASE_REVIEWS_TABLE_NAME", "reviews")
SUPABASE_ENABLED = bool(SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY and SUPABASE_TABLE_NAME)

PUBLIC_REVIEWS_URL = os.getenv("PUBLIC_REVIEWS_URL", "https://transfer-bot-c5yn.onrender.com/reviews")
PUBLIC_BOT_URL = os.getenv("PUBLIC_BOT_URL", "")
PUBLIC_SITE_TITLE = os.getenv("PUBLIC_SITE_TITLE", "Трансферы из Батуми")

BOT_TIMEZONE = os.getenv("BOT_TIMEZONE", "Asia/Tbilisi")
BOT_TZ = ZoneInfo(BOT_TIMEZONE)

REMINDER_CHECK_SECONDS = int(os.getenv("REMINDER_CHECK_SECONDS", "300"))
LIVE_TRACKING_SECONDS = int(os.getenv("LIVE_TRACKING_SECONDS", "3600"))

PUBLIC_PAYMENT_URL = os.getenv("PUBLIC_PAYMENT_URL", "https://transfer-bot-c5yn.onrender.com/pay")

PAYMENT_BANK_RECEIVER = os.getenv("PAYMENT_BANK_RECEIVER", "")
PAYMENT_BANK_NAME = os.getenv("PAYMENT_BANK_NAME", "Credo Bank")
PAYMENT_BANK_GEL_IBAN = os.getenv("PAYMENT_BANK_GEL_IBAN", "")
PAYMENT_BANK_USD_IBAN = os.getenv("PAYMENT_BANK_USD_IBAN", "")
PAYMENT_BANK_EUR_IBAN = os.getenv("PAYMENT_BANK_EUR_IBAN", "")

PAYMENT_RUB_RECEIVER = os.getenv("PAYMENT_RUB_RECEIVER", "Яковлев Андрей Русланович")
PAYMENT_RUB_BANK = os.getenv("PAYMENT_RUB_BANK", "Яндекс Банк")
PAYMENT_RUB_PHONE = os.getenv("PAYMENT_RUB_PHONE", "+7(950)493-96-63")

PAYMENT_TG_WALLET = os.getenv("PAYMENT_TG_WALLET", "https://t.me/BatumiTransferBot")
PAYMENT_CRYPTO_USDT_TRC20 = os.getenv("PAYMENT_CRYPTO_USDT_TRC20", "TH9BE3DhPCpoyGe93iQeMYhAbJWHptiH5y")
PAYMENT_CRYPTO_USDT_TON = os.getenv("PAYMENT_CRYPTO_USDT_TON", "UQC3VjQS0-5Vpgkf29C583OKaz1GBHXxtLnYIro0cuG4QTzv")

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


FAQ_ITEMS = {
    "💳 Предоплата": (
        "💳 Когда возвращается предоплата?\n\n"
        "Предоплата возвращается полностью, если поездка не состоялась по нашей стороне: "
        "водитель не смог приехать, машина не была найдена или мы сами отменили заказ.\n\n"
        "Если клиент отменяет поездку заранее, не позднее чем за 24 часа до выезда, "
        "предоплата возвращается или переносится на другую дату.\n\n"
        "Если отмена меньше чем за 24 часа до выезда, предоплата может быть удержана, "
        "потому что водитель уже зарезервировал время и отказался от других заказов.\n\n"
        "В спорных ситуациях решение принимает менеджер."
    ),
    "🚗 Водитель опоздал": (
        "🚗 Что если водитель опоздал?\n\n"
        "Мы заранее отправляем данные водителя и live-трекинг, чтобы клиент видел машину на карте.\n\n"
        "Если водитель задерживается, менеджер сообщает клиенту причину и новое время прибытия. "
        "Если задержка значительная и клиент не может ждать, мы стараемся найти замену.\n\n"
        "Если задержка произошла по нашей вине и поездка из-за этого сорвалась, "
        "предоплата возвращается или переносится на другой заказ."
    ),
    "⏱ Клиент опоздал": (
        "⏱ Что если клиент опоздал?\n\n"
        "Водитель бесплатно ожидает до 15 минут после согласованного времени.\n\n"
        "Если клиент предупреждает заранее, мы стараемся перенести время или договориться с водителем.\n\n"
        "Если клиент не выходит на связь или сильно опаздывает, водитель может уехать, "
        "а предоплата может быть удержана как компенсация за резерв машины и время водителя."
    ),
    "⛰ Граница закрыта": (
        "⛰ Что если граница закрыта или дорога перекрыта?\n\n"
        "Мы не можем гарантировать прохождение границы, работу КПП, погоду, очереди "
        "и решения пограничных служб.\n\n"
        "Если граница или дорога закрыта до начала поездки, заказ можно перенести "
        "или отменить с возвратом предоплаты.\n\n"
        "Если проблема возникла уже в пути, менеджер связывается с клиентом и водителем. "
        "Возможны ожидание, изменение маршрута, перенос поездки или расчёт фактически выполненной части маршрута."
    ),
    "🧳 Много багажа": (
        "🧳 Что если много багажа?\n\n"
        "Сообщите о багаже заранее при оформлении заказа.\n\n"
        "Стандартно считается обычный багаж пассажира: чемодан или сумка на человека.\n\n"
        "Если есть крупный багаж, коробки, детская коляска, животное, спортивное снаряжение "
        "или посылки, это нужно указать до подтверждения поездки.\n\n"
        "Если багаж не был указан заранее и не помещается в машину, может потребоваться "
        "доплата, замена автомобиля или второй автомобиль."
    ),
}

FAQ_MENU_TEXT = (
    "📄 Правила и FAQ\n\n"
    "Выберите вопрос, который хотите открыть:"
)

FAQ_NOTICE_TEXT = (
    "⚠️ Финальные условия по нестандартным ситуациям подтверждает менеджер до поездки."
)


HELP_KB = ReplyKeyboardMarkup(
    [
        ["📄 Правила и FAQ"],
        ["✍️ Написать менеджеру"],
        ["⬅️ Назад"],
    ],
    resize_keyboard=True,
)


FAQ_KB = ReplyKeyboardMarkup(
    [
        ["💳 Предоплата"],
        ["🚗 Водитель опоздал"],
        ["⏱ Клиент опоздал"],
        ["⛰ Граница закрыта"],
        ["🧳 Много багажа"],
        ["✍️ Написать менеджеру"],
        ["⬅️ Назад"],
    ],
    resize_keyboard=True,
)


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
    return datetime.now(BOT_TZ).isoformat(timespec="seconds")


def status_label(status: str) -> str:
    return STATUS_LABELS.get(status or "", status or "не указан")


def parse_trip_datetime(text: str):
    raw = text.strip()
    current_year = datetime.now(BOT_TZ).year

    formats = [
        ("%d.%m.%Y %H:%M", False),
        ("%d.%m.%y %H:%M", False),
        ("%d.%m %H:%M", True),
    ]

    for fmt, add_year in formats:
        try:
            dt = datetime.strptime(raw, fmt)

            if add_year:
                dt = dt.replace(year=current_year)

                # Если дата уже сильно в прошлом, считаем, что человек имел в виду следующий год.
                if dt.replace(tzinfo=BOT_TZ) < datetime.now(BOT_TZ) - timedelta(days=2):
                    dt = dt.replace(year=current_year + 1)

            dt = dt.replace(tzinfo=BOT_TZ)
            return dt

        except ValueError:
            continue

    return None


def format_trip_datetime(dt: datetime) -> str:
    return dt.astimezone(BOT_TZ).strftime("%d.%m.%Y %H:%M")


def parse_supabase_datetime(value: str):
    if not value:
        return None

    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(BOT_TZ)
    except ValueError:
        return None


def reminder_label(reminder_key: str) -> str:
    labels = {
        "reminder_24h_sent": "за 24 часа",
        "reminder_3h_sent": "за 3 часа",
        "reminder_1h_sent": "за 1 час",
    }
    return labels.get(reminder_key, "")


def google_maps_link(lat, lng) -> str:
    return f"https://maps.google.com/?q={lat},{lng}"


def format_location_time(value: str) -> str:
    dt = parse_supabase_datetime(value)
    if not dt:
        return "время не указано"
    return dt.strftime("%d.%m.%Y %H:%M")


def build_driver_location_text(order_or_user: dict) -> str:
    lat = order_or_user.get("driver_lat")
    lng = order_or_user.get("driver_lng")

    if lat in ["", None] or lng in ["", None]:
        return ""

    link = google_maps_link(lat, lng)
    updated_at = order_or_user.get("driver_location_updated_at")
    live_active = order_or_user.get("live_tracking_active")

    title = "📡 Live-геометка водителя:" if live_active else "📍 Последняя геометка водителя:"

    return (
        f"{title}\n"
        f"{link}\n"
        f"Обновлено: {format_location_time(updated_at)}"
    )


def live_session_key(chat_id, message_id) -> str:
    return f"{chat_id}:{message_id}"


def live_until_iso() -> str:
    return (datetime.now(BOT_TZ) + timedelta(seconds=LIVE_TRACKING_SECONDS)).isoformat(timespec="seconds")


def live_minutes_text() -> str:
    minutes = max(1, int(LIVE_TRACKING_SECONDS / 60))
    return f"{minutes} мин."


def build_reminder_text(order: dict, reminder_key: str) -> str:
    pickup_dt = parse_supabase_datetime(order.get("pickup_datetime"))
    pickup_text = format_trip_datetime(pickup_dt) if pickup_dt else order.get("trip_date", "—")

    return (
        f"⏰ Напоминание о рейсе {reminder_label(reminder_key)}\\n\\n"
        f"🧾 Заказ: {order.get('order_id', '—')}\\n"
        f"🛣 Направление: {order.get('route', '—')}\\n"
        f"👥 Мест: {order.get('seats', '—')}\\n"
        f"📍 Откуда: {order.get('from_place', '—')}\\n"
        f"🏁 Куда: {order.get('to_place', '—')}\\n"
        f"📅 Дата и время: {pickup_text}\\n"
        f"📊 Статус: {status_label(order.get('status'))}\\n\\n"
        "Актуальный статус можно посмотреть в разделе «📋 Мои заказы»."
    )


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


def supabase_reviews_url(params: str = "") -> str:
    return f"{SUPABASE_URL}/rest/v1/{SUPABASE_REVIEWS_TABLE_NAME}{params}"


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
        "pickup_datetime": str(user.get("pickup_datetime", "")),
        "reminder_24h_sent": bool(user.get("reminder_24h_sent", False)),
        "reminder_3h_sent": bool(user.get("reminder_3h_sent", False)),
        "reminder_1h_sent": bool(user.get("reminder_1h_sent", False)),
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
        "driver_location_updated_at": str(user.get("driver_location_updated_at", "")),
        "live_tracking_active": bool(user.get("live_tracking_active", False)),
        "live_started_at": str(user.get("live_started_at", "")),
        "live_until": str(user.get("live_until", "")),
        "live_stopped_at": str(user.get("live_stopped_at", "")),
        "driver_live_chat_id": str(user.get("driver_live_chat_id", "")),
        "driver_live_message_id": int(user.get("driver_live_message_id")) if str(user.get("driver_live_message_id", "")).isdigit() else None,
        "client_live_message_id": int(user.get("client_live_message_id")) if str(user.get("client_live_message_id", "")).isdigit() else None,
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


def patch_order_fields(order_id: str, fields: dict):
    if not SUPABASE_ENABLED or not order_id:
        return None

    fields["updated_at"] = now_iso()

    try:
        response = requests.patch(
            supabase_table_url(f"?order_id=eq.{order_id}"),
            headers=supabase_headers("return=representation"),
            json=fields,
            timeout=12,
        )

        if response.status_code >= 400:
            print(f"SUPABASE PATCH ERROR {response.status_code}: {response.text}", flush=True)
            return None

        return response.json()

    except Exception as exc:
        print(f"SUPABASE PATCH EXCEPTION: {exc}", flush=True)
        return None


def public_client_name(name: str) -> str:
    raw = (name or "").strip()

    if not raw:
        return "Клиент"

    raw = raw.split("(@")[0].strip()
    raw = raw.split("@")[0].strip()
    first = raw.split()[0] if raw.split() else "Клиент"

    return first[:24]


def create_review(user_id: int, user: dict, rating: int, comment: str = ""):
    if not SUPABASE_ENABLED:
        print("SUPABASE DISABLED: review not saved", flush=True)
        return None

    order_id = str(user.get("review_order_id") or user.get("order_id") or "")
    order = fetch_order_by_order_id(order_id) if order_id else None

    payload = {
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "order_id": order_id,
        "telegram_id": str(user_id),
        "client_name": str(user.get("client_name") or (order or {}).get("client_name") or "Клиент"),
        "route": str(user.get("route") or (order or {}).get("route") or ""),
        "rating": int(rating),
        "comment": str(comment or "").strip(),
        "is_public": True,
        "is_approved": True,
    }

    payload = {
        key: value
        for key, value in payload.items()
        if value not in [None, ""]
    }

    try:
        response = requests.post(
            supabase_reviews_url(),
            headers=supabase_headers("return=representation"),
            json=payload,
            timeout=12,
        )

        if response.status_code >= 400:
            print(f"SUPABASE REVIEW CREATE ERROR {response.status_code}: {response.text}", flush=True)
            return None

        data = response.json()
        if isinstance(data, list) and data:
            return data[0]

        return None

    except Exception as exc:
        print(f"SUPABASE REVIEW CREATE EXCEPTION: {exc}", flush=True)
        return None


def fetch_public_reviews(limit: int = 50):
    if not SUPABASE_ENABLED:
        return []

    try:
        params = (
            "?is_public=eq.true"
            "&is_approved=eq.true"
            "&select=rating,comment,client_name,route,created_at"
            "&order=created_at.desc"
            f"&limit={limit}"
        )

        response = requests.get(
            supabase_reviews_url(params),
            headers=supabase_headers(),
            timeout=12,
        )

        if response.status_code >= 400:
            print(f"SUPABASE REVIEWS FETCH ERROR {response.status_code}: {response.text}", flush=True)
            return []

        return response.json()

    except Exception as exc:
        print(f"SUPABASE REVIEWS FETCH EXCEPTION: {exc}", flush=True)
        return []


def render_reviews_html() -> str:
    reviews = fetch_public_reviews(limit=80)

    cards = []

    for review in reviews:
        rating = int(review.get("rating") or 0)
        stars = "⭐" * max(1, min(5, rating))
        name = html.escape(public_client_name(review.get("client_name")))
        route = html.escape(review.get("route") or "Маршрут не указан")
        comment = html.escape((review.get("comment") or "Оценка без комментария").strip())

        cards.append(
            f"""
            <article class="card">
                <div class="stars">{stars}</div>
                <p class="comment">{comment}</p>
                <div class="meta">{name} · {route}</div>
            </article>
            """
        )

    if not cards:
        cards.append(
            """
            <article class="card empty">
                <div class="stars">⭐</div>
                <p class="comment">Отзывы скоро появятся после первых завершённых поездок.</p>
                <div class="meta">Трансферы из Батуми</div>
            </article>
            """
        )

    cta = ""
    if PUBLIC_BOT_URL:
        safe_bot_url = html.escape(PUBLIC_BOT_URL)
        cta = f'<a class="button" href="{safe_bot_url}">Заказать трансфер в Telegram</a>'

    title = html.escape(PUBLIC_SITE_TITLE)

    return f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Отзывы — {title}</title>
  <style>
    body {{
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
      background: #f5f5f5;
      color: #171717;
    }}
    .wrap {{
      max-width: 920px;
      margin: 0 auto;
      padding: 32px 16px 48px;
    }}
    .hero {{
      background: #111827;
      color: #fff;
      border-radius: 24px;
      padding: 28px;
      margin-bottom: 22px;
    }}
    .hero h1 {{
      margin: 0 0 10px;
      font-size: 32px;
      line-height: 1.1;
    }}
    .hero p {{
      margin: 0;
      color: #d1d5db;
      font-size: 16px;
      line-height: 1.5;
    }}
    .button {{
      display: inline-block;
      margin-top: 18px;
      padding: 12px 16px;
      border-radius: 14px;
      background: #22c55e;
      color: #07130b;
      font-weight: 700;
      text-decoration: none;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: 16px;
    }}
    .card {{
      background: white;
      border-radius: 20px;
      padding: 20px;
      box-shadow: 0 8px 28px rgba(0,0,0,.06);
    }}
    .stars {{
      font-size: 20px;
      margin-bottom: 12px;
    }}
    .comment {{
      font-size: 16px;
      line-height: 1.5;
      margin: 0 0 16px;
      white-space: pre-wrap;
    }}
    .meta {{
      color: #6b7280;
      font-size: 14px;
    }}
    .empty {{
      grid-column: 1 / -1;
    }}
    .footer {{
      margin-top: 24px;
      color: #6b7280;
      font-size: 13px;
      text-align: center;
    }}
  </style>
</head>
<body>
  <main class="wrap">
    <section class="hero">
      <h1>Отзывы клиентов</h1>
      <p>{title}: трансферы, посылки, водитель заранее, статусы поездки и live-трекинг.</p>
      {cta}
    </section>
    <section class="grid">
      {''.join(cards)}
    </section>
    <div class="footer">Отзывы оставляют клиенты после завершённой поездки.</div>
  </main>
</body>
</html>"""


def fetch_order_by_order_id(order_id: str):
    if not SUPABASE_ENABLED or not order_id:
        return None

    try:
        params = (
            f"?order_id=eq.{order_id}"
            "&select=order_id,telegram_id,client_name,route,seats,from_place,to_place,trip_date,pickup_datetime,"
            "status,price_gel,deposit_gel,price_usd,price_eur,price_rub,driver_live_chat_id,driver_live_message_id,"
            "client_live_message_id,live_tracking_active"
            "&limit=1"
        )

        response = requests.get(
            supabase_table_url(params),
            headers=supabase_headers(),
            timeout=12,
        )

        if response.status_code >= 400:
            print(f"SUPABASE ORDER FETCH ERROR {response.status_code}: {response.text}", flush=True)
            return None

        data = response.json()
        if data:
            return data[0]

        return None

    except Exception as exc:
        print(f"SUPABASE ORDER FETCH EXCEPTION: {exc}", flush=True)
        return None


def fetch_order_by_driver_live(chat_id, message_id):
    if not SUPABASE_ENABLED:
        return None

    try:
        params = (
            f"?driver_live_chat_id=eq.{chat_id}"
            f"&driver_live_message_id=eq.{message_id}"
            "&live_tracking_active=eq.true"
            "&select=order_id,telegram_id,status,route,seats,from_place,to_place,trip_date,"
            "driver_lat,driver_lng,driver_location_updated_at,client_live_message_id,live_tracking_active"
            "&limit=1"
        )

        response = requests.get(
            supabase_table_url(params),
            headers=supabase_headers(),
            timeout=12,
        )

        if response.status_code >= 400:
            print(f"SUPABASE LIVE FETCH ERROR {response.status_code}: {response.text}", flush=True)
            return None

        data = response.json()
        if data:
            return data[0]

        return None

    except Exception as exc:
        print(f"SUPABASE LIVE FETCH EXCEPTION: {exc}", flush=True)
        return None


def fetch_orders_for_reminders(limit: int = 200):
    if not SUPABASE_ENABLED:
        return []

    try:
        params = (
            "?pickup_datetime=not.is.null"
            "&status=in.(reserved,driver_assigned,driver_on_way,driver_arrived,passenger_picked,in_progress)"
            "&select=order_id,telegram_id,status,route,seats,from_place,to_place,trip_date,pickup_datetime,"
            "reminder_24h_sent,reminder_3h_sent,reminder_1h_sent"
            "&order=pickup_datetime.asc"
            f"&limit={limit}"
        )

        response = requests.get(
            supabase_table_url(params),
            headers=supabase_headers(),
            timeout=12,
        )

        if response.status_code >= 400:
            print(f"SUPABASE REMINDERS FETCH ERROR {response.status_code}: {response.text}", flush=True)
            return []

        return response.json()

    except Exception as exc:
        print(f"SUPABASE REMINDERS FETCH EXCEPTION: {exc}", flush=True)
        return []


def due_reminder_key(order: dict, now_dt: datetime):
    pickup_dt = parse_supabase_datetime(order.get("pickup_datetime"))
    if not pickup_dt:
        return None

    remaining = pickup_dt - now_dt

    if remaining < timedelta(minutes=-30):
        return None

    if (
        remaining <= timedelta(hours=1)
        and not order.get("reminder_1h_sent")
    ):
        return "reminder_1h_sent"

    if (
        remaining <= timedelta(hours=3)
        and remaining > timedelta(hours=1)
        and not order.get("reminder_3h_sent")
    ):
        return "reminder_3h_sent"

    if (
        remaining <= timedelta(hours=24)
        and remaining > timedelta(hours=3)
        and not order.get("reminder_24h_sent")
    ):
        return "reminder_24h_sent"

    return None


async def reminder_loop(application):
    print("REMINDER LOOP STARTED", flush=True)

    while True:
        try:
            if SUPABASE_ENABLED:
                now_dt = datetime.now(BOT_TZ)
                orders = fetch_orders_for_reminders()

                for order in orders:
                    key = due_reminder_key(order, now_dt)

                    if not key:
                        continue

                    telegram_id = order.get("telegram_id")
                    order_id = order.get("order_id")

                    if not telegram_id or not order_id:
                        continue

                    try:
                        await application.bot.send_message(
                            chat_id=int(telegram_id),
                            text=build_reminder_text(order, key),
                        )

                        patch_order_fields(order_id, {key: True})
                        print(f"REMINDER SENT {key} ORDER {order_id}", flush=True)

                    except Exception as exc:
                        print(f"REMINDER SEND ERROR ORDER {order_id}: {exc}", flush=True)

        except Exception as exc:
            print(f"REMINDER LOOP ERROR: {exc}", flush=True)

        await asyncio.sleep(REMINDER_CHECK_SECONDS)


async def post_init(application):
    application.create_task(reminder_loop(application))


def fetch_user_orders(user_id: int, limit: int = 10):
    if not SUPABASE_ENABLED:
        return None

    try:
        params = (
            f"?telegram_id=eq.{user_id}"
            "&select=order_id,status,route,seats,from_place,to_place,trip_date,pickup_datetime,comment,"
            "price_gel,deposit_gel,driver_name,driver_phone,driver_info,driver_id,driver_lat,driver_lng,driver_location_updated_at,live_tracking_active,live_until,updated_at,created_at"
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
        f"📅 Дата: {format_trip_datetime(parse_supabase_datetime(order.get('pickup_datetime'))) if order.get('pickup_datetime') else order.get('trip_date', '—')}",
        f"💰 Цена: {price_text}",
    ]

    driver_info = order.get("driver_info")
    if driver_info:
        lines.append(f"🚗 Водитель/машина: {driver_info}")

    location_text = build_driver_location_text(order)
    if location_text:
        lines.append(location_text)

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


async def stop_live_tracking(client_id: int, context: ContextTypes.DEFAULT_TYPE, reason: str = ""):
    user = get_user(client_id)
    order_id = user.get("order_id")
    order = fetch_order_by_order_id(order_id) if order_id else None

    client_live_message_id = (
        user.get("client_live_message_id")
        or (order or {}).get("client_live_message_id")
    )

    driver_live_chat_id = (
        user.get("driver_live_chat_id")
        or (order or {}).get("driver_live_chat_id")
    )

    driver_live_message_id = (
        user.get("driver_live_message_id")
        or (order or {}).get("driver_live_message_id")
    )

    # Stop the live map shown to the client.
    if client_live_message_id:
        try:
            await context.bot.stop_message_live_location(
                chat_id=client_id,
                message_id=int(client_live_message_id),
            )
        except Exception as exc:
            print(f"STOP CLIENT LIVE LOCATION ERROR: {exc}", flush=True)

    # Remove in-memory session so further driver live updates don't reactivate the order.
    if driver_live_chat_id and driver_live_message_id:
        session_key = live_session_key(driver_live_chat_id, driver_live_message_id)
        context.application.bot_data.setdefault("live_sessions", {}).pop(session_key, None)

    user["live_tracking_active"] = False
    user["live_stopped_at"] = now_iso()

    if order_id:
        patch_order_fields(
            order_id,
            {
                "live_tracking_active": False,
                "live_stopped_at": user["live_stopped_at"],
            },
        )

    print(
        f"LIVE TRACKING STOPPED client_id={client_id} order_id={order_id} reason={reason}",
        flush=True,
    )


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
                InlineKeyboardButton("📡 Live-трекинг", callback_data=f"live_{client_id}"),
                InlineKeyboardButton("⛔ Стоп live", callback_data=f"live_stop_{client_id}"),
            ],
            [
                InlineKeyboardButton("📍 Геометка", callback_data=f"geo_{client_id}"),
            ],
            [
                InlineKeyboardButton("✉️ Ответить клиенту", callback_data=f"reply_{client_id}"),
            ],
        ]
    )


async def send_review_request(client_id: int, user: dict, context: ContextTypes.DEFAULT_TYPE):
    order_id = str(user.get("order_id", ""))

    if not order_id:
        return

    text = (
        "⭐ Поделитесь впечатлением о поездке.\n\n"
        "Оцените рейс от 1 до 5. После оценки можно будет оставить короткий комментарий.\n\n"
        "Отзывы помогают новым клиентам понять, что сервису можно доверять."
    )

    await context.bot.send_message(
        chat_id=client_id,
        text=text,
        reply_markup=review_rating_keyboard(client_id, order_id),
    )


async def set_trip_status(client_id: int, status: str, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(client_id)
    user["status"] = status

    if status in ["completed", "cancelled", "rejected", "expired"]:
        await stop_live_tracking(client_id, context, reason=f"terminal_status:{status}")

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

    if status == "completed":
        await send_review_request(client_id, user, context)



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


def money(value, currency: str) -> str:
    try:
        amount = float(value)
    except (TypeError, ValueError):
        amount = 0

    if currency == "RUB":
        return f"{round(amount):,.0f} RUB".replace(",", " ")

    return f"{amount:,.2f} {currency}".replace(",", " ")


def payment_link_for_order(order_id: str) -> str:
    base = PUBLIC_PAYMENT_URL.rstrip("/")
    return f"{base}?order_id={order_id}"


def safe_html(value) -> str:
    return html.escape(str(value or ""))


def format_payment_detail(value: str, fallback: str = "уточнит менеджер") -> str:
    value = (value or "").strip()
    return safe_html(value if value else fallback)


def render_payment_html(order_id: str) -> str:
    order = fetch_order_by_order_id(order_id)

    if not order:
        return """<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Оплата заказа</title>
  <style>
    body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;background:#f5f5f5;color:#171717;margin:0}
    .wrap{max-width:760px;margin:0 auto;padding:32px 16px}
    .card{background:#fff;border-radius:22px;padding:24px;box-shadow:0 8px 28px rgba(0,0,0,.06)}
  </style>
</head>
<body>
  <main class="wrap">
    <section class="card">
      <h1>Заказ не найден</h1>
      <p>Проверьте ссылку или вернитесь в Telegram и запросите ссылку заново.</p>
    </section>
  </main>
</body>
</html>"""

    deposit_gel = order.get("deposit_gel")

    try:
        deposit_gel = float(deposit_gel)
    except (TypeError, ValueError):
        price_gel = order.get("price_gel")
        try:
            deposit_gel = round(float(price_gel) * 0.5, 2)
        except (TypeError, ValueError):
            deposit_gel = 0

    deposit_usd = convert_price(deposit_gel, "USD")
    deposit_eur = convert_price(deposit_gel, "EUR")
    deposit_rub = convert_price(deposit_gel, "RUB")

    bot_button = ""
    if PUBLIC_BOT_URL:
        bot_button = f'<a class="button" href="{safe_html(PUBLIC_BOT_URL)}">Вернуться в Telegram</a>'

    bank_receiver = format_payment_detail(PAYMENT_BANK_RECEIVER, "будет указан менеджером")
    gel_iban = format_payment_detail(PAYMENT_BANK_GEL_IBAN, "будет добавлен после открытия счёта")
    usd_iban = format_payment_detail(PAYMENT_BANK_USD_IBAN, "будет добавлен после открытия счёта")
    eur_iban = format_payment_detail(PAYMENT_BANK_EUR_IBAN, "будет добавлен после открытия счёта")

    return f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Оплата заказа №{safe_html(order_id)}</title>
  <style>
    body {{
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
      background: #f5f5f5;
      color: #171717;
    }}
    .wrap {{
      max-width: 920px;
      margin: 0 auto;
      padding: 28px 16px 48px;
    }}
    .hero {{
      background: #111827;
      color: white;
      border-radius: 24px;
      padding: 26px;
      margin-bottom: 18px;
    }}
    .hero h1 {{
      margin: 0 0 12px;
      font-size: 30px;
      line-height: 1.1;
    }}
    .hero p {{
      margin: 6px 0;
      color: #e5e7eb;
      line-height: 1.45;
    }}
    .summary {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
      gap: 12px;
      margin-top: 18px;
    }}
    .sum-card {{
      background: rgba(255,255,255,.1);
      border: 1px solid rgba(255,255,255,.16);
      border-radius: 16px;
      padding: 14px;
    }}
    .sum-card .label {{
      font-size: 13px;
      color: #cbd5e1;
      margin-bottom: 6px;
    }}
    .sum-card .value {{
      font-size: 20px;
      font-weight: 800;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 16px;
    }}
    .card {{
      background: white;
      border-radius: 22px;
      padding: 22px;
      box-shadow: 0 8px 28px rgba(0,0,0,.06);
    }}
    .card h2 {{
      margin: 0 0 14px;
      font-size: 22px;
    }}
    .line {{
      margin: 10px 0;
      line-height: 1.45;
    }}
    .mono {{
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      background: #f3f4f6;
      border-radius: 10px;
      padding: 10px;
      overflow-wrap: anywhere;
    }}
    .warn {{
      margin-top: 16px;
      background: #fff7ed;
      border: 1px solid #fed7aa;
      color: #7c2d12;
      border-radius: 16px;
      padding: 14px;
      line-height: 1.45;
    }}
    .button {{
      display: inline-block;
      margin-top: 16px;
      padding: 13px 16px;
      border-radius: 14px;
      background: #22c55e;
      color: #07130b;
      font-weight: 800;
      text-decoration: none;
    }}
    .footer {{
      margin-top: 18px;
      color: #6b7280;
      text-align: center;
      font-size: 13px;
    }}
  </style>
</head>
<body>
  <main class="wrap">
    <section class="hero">
      <h1>Оплата заказа №{safe_html(order_id)}</h1>
      <p>🛣 Маршрут: <strong>{safe_html(order.get("route") or "не указан")}</strong></p>
      <p>👥 Мест: <strong>{safe_html(order.get("seats") or "—")}</strong></p>
      <p>📅 Дата: <strong>{safe_html(order.get("trip_date") or "—")}</strong></p>
      <p>После оплаты вернитесь в Telegram и нажмите «💳 Я оплатил». Менеджер проверит оплату и закрепит место.</p>
      {bot_button}

      <div class="summary">
        <div class="sum-card"><div class="label">Предоплата GEL</div><div class="value">{money(deposit_gel, "GEL")}</div></div>
        <div class="sum-card"><div class="label">USD</div><div class="value">{money(deposit_usd, "USD")}</div></div>
        <div class="sum-card"><div class="label">EUR</div><div class="value">{money(deposit_eur, "EUR")}</div></div>
        <div class="sum-card"><div class="label">RUB</div><div class="value">{money(deposit_rub, "RUB")}</div></div>
      </div>
    </section>

    <section class="grid">
      <article class="card">
        <h2>🇬🇪 GEL / USD / EUR</h2>
        <div class="line"><strong>Банк:</strong> {format_payment_detail(PAYMENT_BANK_NAME, "Credo Bank")}</div>
        <div class="line"><strong>Получатель:</strong> {bank_receiver}</div>
        <div class="line"><strong>IBAN GEL:</strong><div class="mono">{gel_iban}</div></div>
        <div class="line"><strong>IBAN USD:</strong><div class="mono">{usd_iban}</div></div>
        <div class="line"><strong>IBAN EUR:</strong><div class="mono">{eur_iban}</div></div>
        <div class="line"><strong>Назначение:</strong><div class="mono">Order {safe_html(order_id)}</div></div>
        <div class="warn">Грузинский банк пока в подготовке. Если реквизиты ещё не указаны, запросите их у менеджера в Telegram.</div>
      </article>

      <article class="card">
        <h2>🇷🇺 RUB через СБП</h2>
        <div class="line"><strong>Сумма:</strong> {money(deposit_rub, "RUB")}</div>
        <div class="line"><strong>Получатель:</strong> {format_payment_detail(PAYMENT_RUB_RECEIVER)}</div>
        <div class="line"><strong>Банк:</strong> {format_payment_detail(PAYMENT_RUB_BANK)}</div>
        <div class="line"><strong>Телефон СБП:</strong><div class="mono">{format_payment_detail(PAYMENT_RUB_PHONE)}</div></div>
        <div class="line"><strong>Комментарий:</strong><div class="mono">Order {safe_html(order_id)}</div></div>
        <div class="warn">Обязательно укажите номер заказа в комментарии, иначе оплату придётся искать вручную.</div>
      </article>

      <article class="card">
        <h2>₿ Telegram Wallet / Crypto</h2>
        <div class="line"><strong>Telegram Wallet:</strong><div class="mono">{format_payment_detail(PAYMENT_TG_WALLET)}</div></div>
        <div class="line"><strong>USDT TRC20:</strong><div class="mono">{format_payment_detail(PAYMENT_CRYPTO_USDT_TRC20)}</div></div>
        <div class="line"><strong>USDT TON:</strong><div class="mono">{format_payment_detail(PAYMENT_CRYPTO_USDT_TON)}</div></div>
        <div class="line"><strong>Комментарий / memo:</strong><div class="mono">Order {safe_html(order_id)}</div></div>
        <div class="warn">Внимательно выбирайте сеть. USDT TRC20 отправлять только в TRON/TRC20. USDT TON отправлять только в TON. При ошибке сети платёж может быть потерян.</div>
      </article>
    </section>

    <div class="footer">Оплата подтверждается менеджером вручную после нажатия кнопки «Я оплатил» в Telegram.</div>
  </main>
</body>
</html>"""


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

    payment_link = payment_link_for_order(user.get("order_id", ""))

    await context.bot.send_message(
        chat_id=client_id,
        text=(
            "💳 БРОНИРОВАНИЕ МЕСТА\n\n"
            f"💰 Общая цена:\n{format_multicurrency(price)}\n\n"
            f"💵 Предоплата 50%:\n{format_multicurrency(deposit)}\n\n"
            f"🔗 Оплатить: {payment_link}\n\n"
            "⚠️ После оплаты место будет закреплено.\n"
            "Правила возврата предоплаты и опозданий доступны в разделе «❓ Помощь»."
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
        ["📋 Мои заказы", "⭐ Отзывы"],
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


def review_rating_keyboard(client_id: int, order_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("⭐ 5", callback_data=f"review_rate_5_{client_id}_{order_id}"),
                InlineKeyboardButton("⭐ 4", callback_data=f"review_rate_4_{client_id}_{order_id}"),
                InlineKeyboardButton("⭐ 3", callback_data=f"review_rate_3_{client_id}_{order_id}"),
            ],
            [
                InlineKeyboardButton("⭐ 2", callback_data=f"review_rate_2_{client_id}_{order_id}"),
                InlineKeyboardButton("⭐ 1", callback_data=f"review_rate_1_{client_id}_{order_id}"),
            ],
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
        user["pickup_datetime"] = ""
        user["reminder_24h_sent"] = False
        user["reminder_3h_sent"] = False
        user["reminder_1h_sent"] = False
        user["route"] = ""
        user["price_data"] = None
        user["total_price_gel"] = None

        await update.message.reply_text("Сколько мест необходимо?")
        return

    if text == "💰 Цены":
        await update.message.reply_text(
            "💰 Цены за машину:\n\n"
            "Батуми ↔ аэропорт Батуми от 59 GEL\n"
            "Батуми ↔ Тбилиси — от 399 GEL\n"
            "Батуми ↔ Кутаиси — от 249 GEL\n\n"
            "Батуми ↔ Сарпи — от 79 GEL\n\n"
            "Почасовая по Батуми от 59 GEL\n\n"
            "Почасовая за городом — от 79 GEL\n\n"
            "Аренда водителя на сутки — от 649 GEL\n\n"
            "Суточная межгород — от 749 GEL\n\n"
            

            ```
        "🚘 Тарифы указаны за машину Lexus ES300, до 3 пассажиров.\n"
        "Это частный премиум-трансфер, не сборная поездка по местам.\n"
        "В стоимость включены 1–2 стандартных чемодана.\n"
        "Обратное направление считается по тому же тарифу.\n"
        "Если пассажиров больше 3, нужен минивен — выберите «✍️ Свой маршрут» при заказе, менеджер рассчитает стоимость.\n"
        "Если нужного направления нет в списке, выберите «✍️ Свой маршрут» при заказе.\n"
        "Финальная цена зависит от даты, времени подачи, багажа, ожидания, дополнительных остановок и пограничных условий.\n\n"
        "Правила по предоплате, опозданиям, границе и багажу доступны в разделе «❓ Помощь»."
```

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

    if text == "⭐ Отзывы":
        await update.message.reply_text(
            "⭐ Отзывы клиентов можно посмотреть здесь:\n"
            f"{PUBLIC_REVIEWS_URL}",
            reply_markup=MENU,
        )
        return

    if text == "❓ Помощь":
        user["step"] = None
        user["client_name"] = get_client_name(update.message.from_user)
        user["client_url"] = get_client_url(update.message.from_user)

        await update.message.reply_text(
            FAQ_MENU_TEXT,
            reply_markup=FAQ_KB,
        )
        return

    if text == "📄 Правила и FAQ":
        user["step"] = None
        await update.message.reply_text(
            FAQ_MENU_TEXT,
            reply_markup=FAQ_KB,
        )
        return

    if text in FAQ_ITEMS:
        user["step"] = None
        await update.message.reply_text(
            FAQ_ITEMS[text] + "\n\n" + FAQ_NOTICE_TEXT,
            reply_markup=FAQ_KB,
        )
        return

    if text == "✍️ Написать менеджеру":
        user["step"] = "support_question"
        user["client_name"] = get_client_name(update.message.from_user)
        user["client_url"] = get_client_url(update.message.from_user)

        await update.message.reply_text(
            "Напишите ваш вопрос одним сообщением.\n"
            "Я передам его менеджеру 🚕\n\n"
            "Чтобы вернуться в меню, нажмите «⬅️ Назад».",
            reply_markup=FAQ_KB,
        )
        return

    if text == "⬅️ Назад":
        user["step"] = None
        await update.message.reply_text("Меню:", reply_markup=MENU)
        return

    # REVIEW COMMENT
    if step == "review_comment":
        rating = user.get("review_rating")
        order_id = user.get("review_order_id")
        comment = text.strip()

        if comment in ["-", "Без комментария", "без комментария"]:
            comment = ""

        if not rating or not order_id:
            user["step"] = None
            await update.message.reply_text(
                "Не удалось сохранить отзыв: потеряны данные заказа.\n"
                "Можете написать менеджеру, и мы добавим отзыв вручную.",
                reply_markup=MENU,
            )
            return

        review = create_review(
            user_id=user_id,
            user=user,
            rating=int(rating),
            comment=comment,
        )

        user["step"] = None
        user.pop("review_rating", None)
        user.pop("review_order_id", None)

        if review:
            await update.message.reply_text(
                "✅ Спасибо за отзыв!\n\n"
                "Он появится на странице отзывов после сохранения.",
                reply_markup=MENU,
            )

            await context.bot.send_message(
                chat_id=ADMIN_CHAT_ID,
                text=(
                    "⭐ НОВЫЙ ОТЗЫВ\n\n"
                    f"👤 Клиент: {user.get('client_name', 'Клиент')}\n"
                    f"🧾 Заказ: {order_id}\n"
                    f"🛣 Маршрут: {user.get('route', '—')}\n"
                    f"⭐ Оценка: {rating}/5\n"
                    f"💬 Отзыв: {comment or 'без комментария'}\n\n"
                    f"🌐 Страница отзывов: {PUBLIC_REVIEWS_URL}"
                ),
            )
        else:
            await update.message.reply_text(
                "❌ Не удалось сохранить отзыв.\n"
                "Проверьте подключение Supabase или таблицу reviews.",
                reply_markup=MENU,
            )
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
        await update.message.reply_text(
            "Введите дату и время рейса в формате:\n\n"
            "25.06 14:30\n"
            "или\n"
            "25.06.2026 14:30\n\n"
            "Это нужно для автоматических напоминаний пассажиру."
        )
        return

    # DATE
    if step == "date":
        pickup_dt = parse_trip_datetime(text)

        if not pickup_dt:
            await update.message.reply_text(
                "Не понял дату. Введите строго в формате:\n\n"
                "25.06 14:30\n"
                "или\n"
                "25.06.2026 14:30"
            )
            return

        user["pickup_datetime"] = pickup_dt.isoformat()
        user["date"] = format_trip_datetime(pickup_dt)
        user["reminder_24h_sent"] = False
        user["reminder_3h_sent"] = False
        user["reminder_1h_sent"] = False
        user["step"] = "comment"

        await update.message.reply_text(
            "Добавьте комментарий к заказу, если нужно.\n\n"
            "Например: номер рейса, много багажа, детское кресло, животное, "
            "пожелания по остановкам.\n\n"
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

    # CLIENT REVIEW RATING
    if data.startswith("review_rate_"):
        parts = data.split("_", 4)

        if len(parts) != 5:
            await query.message.reply_text("❌ Не удалось обработать оценку.")
            return

        rating = int(parts[2])
        client_id = int(parts[3])
        order_id = parts[4]

        if query.from_user.id != client_id:
            await query.message.reply_text("❌ Это не ваш заказ.")
            return

        user = get_user(client_id)
        order = fetch_order_by_order_id(order_id)

        user["step"] = "review_comment"
        user["review_rating"] = rating
        user["review_order_id"] = order_id

        if order and order.get("route"):
            user["route"] = order.get("route")

        await query.message.reply_text(
            f"Спасибо! Оценка: {rating}/5.\n\n"
            "Напишите короткий отзыв одним сообщением.\n"
            "Если комментарий не нужен, отправьте «-».",
            reply_markup=CONFIRM_KB,
        )
        return

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

    # ADMIN STOP LIVE TRACKING
    if data.startswith("live_stop_"):
        if query.from_user.id not in ADMIN_IDS:
            await query.message.reply_text("❌ Нет доступа")
            return

        client_id = int(data.replace("live_stop_", ""))
        await stop_live_tracking(client_id, context, reason="admin_button")

        await query.message.reply_text(
            "⛔ Live-отслеживание остановлено.",
            reply_markup=status_admin_keyboard(client_id),
        )
        return

    # ADMIN START LIVE TRACKING INPUT
    if data.startswith("live_"):
        if query.from_user.id not in ADMIN_IDS:
            await query.message.reply_text("❌ Нет доступа")
            return

        client_id = int(data.replace("live_", ""))
        context.chat_data["live_for"] = client_id

        await query.message.reply_text(
            "📡 Запуск live-отслеживания.\n\n"
            f"Водитель должен отправить LIVE-геолокацию в этот чат на {live_minutes_text()}.\n\n"
            "Как отправить:\n"
            "📎 → Геопозиция / Location → Делиться геопозицией / Share Live Location.\n\n"
            "После первой live-геометки бот создаст клиенту live-карту и будет обновлять её автоматически."
        )
        return

    # ADMIN START DRIVER GEOLOCATION INPUT
    if data.startswith("geo_"):
        if query.from_user.id not in ADMIN_IDS:
            await query.message.reply_text("❌ Нет доступа")
            return

        client_id = int(data.replace("geo_", ""))
        context.user_data["location_for"] = client_id

        await query.message.reply_text(
            "📍 Отправьте геолокацию водителя следующим сообщением.\n\n"
            "В Telegram нажмите 📎 → Геопозиция / Location → отправить текущую точку.\n\n"
            "После этого клиент получит карту, а геометка сохранится в заказе.\n"
            "Чтобы отменить, напишите: отмена"
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
# ADMIN LOCATION
# =========================

async def admin_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    user_from = update.effective_user

    if not message or not user_from:
        return

    location = message.location
    if not location:
        return

    is_admin_or_group = (
        user_from.id in ADMIN_IDS
        or message.chat_id == ADMIN_CHAT_ID
    )

    if not is_admin_or_group:
        return

    is_live_location = bool(getattr(location, "live_period", None))

    # Existing live session update from driver's edited live location.
    session_key = live_session_key(message.chat_id, message.message_id)
    session = context.application.bot_data.get("live_sessions", {}).get(session_key)

    if not session and is_live_location:
        stored_order = fetch_order_by_driver_live(message.chat_id, message.message_id)
        if stored_order:
            session = {
                "client_id": int(stored_order["telegram_id"]),
                "order_id": stored_order["order_id"],
                "client_live_message_id": stored_order.get("client_live_message_id"),
            }
            context.application.bot_data.setdefault("live_sessions", {})[session_key] = session

    if session:
        client_id = int(session["client_id"])
        user = get_user(client_id)

        if user.get("status") in ["completed", "cancelled", "rejected", "expired"]:
            await stop_live_tracking(client_id, context, reason=f"ignored_live_update_after:{user.get('status')}")
            raise ApplicationHandlerStop

        user["driver_lat"] = location.latitude
        user["driver_lng"] = location.longitude
        user["driver_location_updated_at"] = now_iso()
        user["live_tracking_active"] = True

        patch_order_fields(
            session["order_id"],
            {
                "driver_lat": location.latitude,
                "driver_lng": location.longitude,
                "driver_location_updated_at": user["driver_location_updated_at"],
                "live_tracking_active": True,
            },
        )

        client_live_message_id = session.get("client_live_message_id")

        if client_live_message_id:
            try:
                await context.bot.edit_message_live_location(
                    chat_id=client_id,
                    message_id=int(client_live_message_id),
                    latitude=location.latitude,
                    longitude=location.longitude,
                )
            except Exception as exc:
                print(f"LIVE LOCATION EDIT ERROR: {exc}", flush=True)

        raise ApplicationHandlerStop

    # Start a new live session after admin pressed "📡 Live 1ч".
    if is_live_location and "live_for" in context.chat_data:
        client_id = int(context.chat_data["live_for"])
        user = get_user(client_id)

        live_message = await context.bot.send_location(
            chat_id=client_id,
            latitude=location.latitude,
            longitude=location.longitude,
            live_period=LIVE_TRACKING_SECONDS,
        )

        user["driver_lat"] = location.latitude
        user["driver_lng"] = location.longitude
        user["driver_location_updated_at"] = now_iso()
        user["live_tracking_active"] = True
        user["live_started_at"] = now_iso()
        user["live_until"] = live_until_iso()
        user["driver_live_chat_id"] = str(message.chat_id)
        user["driver_live_message_id"] = message.message_id
        user["client_live_message_id"] = live_message.message_id

        save_order(
            user_id=client_id,
            user=user,
            status=user.get("status") or "driver_on_way",
            notes="Запущено live-отслеживание водителя",
        )

        session_key = live_session_key(message.chat_id, message.message_id)
        context.application.bot_data.setdefault("live_sessions", {})[session_key] = {
            "client_id": client_id,
            "order_id": user.get("order_id"),
            "client_live_message_id": live_message.message_id,
        }

        await context.bot.send_message(
            chat_id=client_id,
            text=(
                f"📡 Live-отслеживание водителя запущено на {live_minutes_text()}.\n\n"
                "Карта выше будет обновляться автоматически, пока водитель делится геолокацией."
            ),
        )

        await message.reply_text(
            "✅ Live-отслеживание запущено.\n"
            "Клиент получил live-карту.",
            reply_markup=status_admin_keyboard(client_id),
        )

        context.chat_data.pop("live_for", None)
        raise ApplicationHandlerStop

    # Normal one-time geolocation mode.
    if "location_for" not in context.user_data:
        return

    client_id = context.user_data["location_for"]

    user = get_user(client_id)
    user["driver_lat"] = location.latitude
    user["driver_lng"] = location.longitude
    user["driver_location_updated_at"] = now_iso()

    save_order(
        user_id=client_id,
        user=user,
        status=user.get("status") or "driver_on_way",
        notes="Обновлена геометка водителя",
    )

    map_link = google_maps_link(location.latitude, location.longitude)

    try:
        await context.bot.send_location(
            chat_id=client_id,
            latitude=location.latitude,
            longitude=location.longitude,
        )

        await context.bot.send_message(
            chat_id=client_id,
            text=(
                "📍 Геометка водителя обновлена.\n\n"
                f"Открыть на карте:\n{map_link}\n\n"
                "Последнюю геометку также можно посмотреть в разделе «📋 Мои заказы»."
            ),
        )

        await message.reply_text(
            "✅ Геометка отправлена клиенту и сохранена в заказе.",
            reply_markup=status_admin_keyboard(client_id),
        )

    except Exception as exc:
        await message.reply_text(
            f"❌ Не удалось отправить геометку клиенту: {exc}"
        )

    context.user_data.pop("location_for", None)
    raise ApplicationHandlerStop


# =========================
# ADMIN PRICE
# =========================

async def admin_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id not in ADMIN_IDS:
        return

    if "live_for" in context.chat_data:
        text = update.message.text.strip().lower()

        if text in ["отмена", "cancel", "❌ отмена"]:
            context.chat_data.pop("live_for", None)
            await update.message.reply_text("Запуск live-отслеживания отменён.")
            raise ApplicationHandlerStop

        await update.message.reply_text(
            "Сейчас ожидается LIVE-геолокация.\n"
            "Нажмите 📎 → Геопозиция / Location → Делиться геопозицией / Share Live Location.\n"
            "Для отмены напишите: отмена"
        )
        raise ApplicationHandlerStop

    if "location_for" in context.user_data:
        text = update.message.text.strip().lower()

        if text in ["отмена", "cancel", "❌ отмена"]:
            context.user_data.pop("location_for", None)
            await update.message.reply_text("Отправка геометки отменена.")
            raise ApplicationHandlerStop

        await update.message.reply_text(
            "Сейчас ожидается геолокация.\n"
            "Нажмите 📎 → Геопозиция / Location → отправить текущую точку.\n"
            "Для отмены напишите: отмена"
        )
        raise ApplicationHandlerStop

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
        path = self.path.split("?", 1)[0].rstrip("/") or "/"

        if path in ["/reviews", "/reviews.html"]:
            body = render_reviews_html().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return

        if path in ["/pay", "/pay.html"]:
            query = parse_qs(urlparse(self.path).query)
            order_id = (query.get("order_id") or [""])[0]
            body = render_payment_html(order_id).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return

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

    app = ApplicationBuilder().token(TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("drivers", drivers_command))

    app.add_handler(CallbackQueryHandler(callbacks))

    app.add_handler(
        MessageHandler(filters.LOCATION, admin_location),
        group=0,
    )

    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, admin_price),
        group=0,
    )

    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, router),
        group=1,
    )

    print("BOT STARTED - PAYMENT PAGE V7 VERSION", flush=True)

    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
