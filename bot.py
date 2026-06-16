from telegram import Update
from telegram.ext import (
    Updater,
    CommandHandler,
    MessageHandler,
    Filters,
    ConversationHandler,
    CallbackContext,
)

import os

TOKEN = os.getenv("BOT_TOKEN")
OWNER_CHAT_ID = int(os.getenv("OWNER_CHAT_ID"))

FROM, TO, DATE, PEOPLE, CONTACT = range(5)


def start(update: Update, context: CallbackContext):
    update.message.reply_text("🚐 Откуда выезжаем?")
    return FROM


def from_city(update: Update, context: CallbackContext):
    context.user_data["from"] = update.message.text
    update.message.reply_text("📍 Куда едем?")
    return TO


def to_city(update: Update, context: CallbackContext):
    context.user_data["to"] = update.message.text
    update.message.reply_text("📅 Дата?")
    return DATE


def date_trip(update: Update, context: CallbackContext):
    context.user_data["date"] = update.message.text
    update.message.reply_text("👥 Пассажиров?")
    return PEOPLE


def people(update: Update, context: CallbackContext):
    context.user_data["people"] = update.message.text
    update.message.reply_text("📱 Контакт?")
    return CONTACT


def contact(update: Update, context: CallbackContext):
    context.user_data["contact"] = update.message.text

    text = f"""
🚐 НОВАЯ ЗАЯВКА

📍 {context.user_data['from']}
📍 {context.user_data['to']}
📅 {context.user_data['date']}
👥 {context.user_data['people']}
📱 {context.user_data['contact']}
"""

    context.bot.send_message(chat_id=OWNER_CHAT_ID, text=text)

    update.message.reply_text("✅ Заявка отправлена!")
    return ConversationHandler.END


def cancel(update: Update, context: CallbackContext):
    update.message.reply_text("❌ Отменено")
    return ConversationHandler.END


def main():
    updater = Updater(TOKEN)
    dp = updater.dispatcher

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            FROM: [MessageHandler(Filters.text, from_city)],
            TO: [MessageHandler(Filters.text, to_city)],
            DATE: [MessageHandler(Filters.text, date_trip)],
            PEOPLE: [MessageHandler(Filters.text, people)],
            CONTACT: [MessageHandler(Filters.text, contact)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    dp.add_handler(conv)

    updater.start_polling()
    updater.idle()


if __name__ == "__main__":
    main()