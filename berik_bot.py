import os
import sqlite3
import logging
from datetime import datetime

from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    ConversationHandler,
    filters,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
PORT = int(os.getenv("PORT", "10000"))

if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")

if not ADMIN_CHAT_ID:
    raise RuntimeError("ADMIN_CHAT_ID is not set")

if not WEBHOOK_URL:
    raise RuntimeError("WEBHOOK_URL is not set")

ADMIN_CHAT_ID = int(ADMIN_CHAT_ID)
DB_PATH = "berik_requests.db"

NAME, PHONE, CITY, SERVICE, DESCRIPTION, PHOTO, CONFIRM = range(7)

MAIN_MENU = ReplyKeyboardMarkup(
    [
        ["📝 Оставить заявку", "💼 Услуги"],
        ["💰 Прайс", "❓ FAQ"],
        ["📞 Связаться с менеджером", "ℹ️ О боте"],
    ],
    resize_keyboard=True,
)

SERVICE_MENU = ReplyKeyboardMarkup(
    [
        ["Консультация", "Разработка Telegram-бота"],
        ["Автоматизация заявок", "Техподдержка"],
        ["⬅️ Назад в меню"],
    ],
    resize_keyboard=True,
)

FAQ_MENU = ReplyKeyboardMarkup(
    [
        ["Сколько стоит?", "Сколько делается?"],
        ["Что нужно от клиента?", "Можно ли доработки?"],
        ["⬅️ Назад в меню"],
    ],
    resize_keyboard=True,
)

PHONE_MENU = ReplyKeyboardMarkup(
    [
        [KeyboardButton("📱 Отправить номер телефона", request_contact=True)],
        ["⬅️ Отмена"],
    ],
    resize_keyboard=True,
    one_time_keyboard=True,
)

YES_NO_SKIP_MENU = ReplyKeyboardMarkup(
    [
        ["Пропустить"],
        ["⬅️ Отмена"],
    ],
    resize_keyboard=True,
    one_time_keyboard=True,
)

CONFIRM_MENU = ReplyKeyboardMarkup(
    [
        ["✅ Подтвердить", "✏️ Заполнить заново"],
        ["⬅️ Отмена"],
    ],
    resize_keyboard=True,
)

ABOUT_TEXT = (
    "Berik — демонстрационный Telegram-бот для приёма заявок.\n\n"
    "Что умеет бот:\n"
    "• показывает услуги\n"
    "• отвечает на частые вопросы\n"
    "• собирает заявки клиентов\n"
    "• отправляет заявку администратору\n"
    "• сохраняет данные в базу SQLite\n\n"
    "Это выглядит как реальный мини-продукт для бизнеса."
)

PRICE_TEXT = (
    "💰 Примерный прайс:\n\n"
    "• Консультация — бесплатно\n"
    "• Простой Telegram-бот — от 50 000 ₸\n"
    "• Бот с заявками и уведомлениями — от 120 000 ₸\n"
    "• Доработки и поддержка — по задаче\n\n"
    "Это демонстрационный прайс. Его можно заменить."
)

SERVICES_TEXT = (
    "💼 Услуги:\n\n"
    "1. Консультация\n"
    "2. Разработка Telegram-бота\n"
    "3. Автоматизация заявок\n"
    "4. Техподдержка"
)

FAQ_ANSWERS = {
    "Сколько стоит?": "Стоимость зависит от задач. Простой бот стоит дешевле, сложный сценарный бот — дороже.",
    "Сколько делается?": "Базового бота можно собрать за 1–3 дня, если структура уже понятна.",
    "Что нужно от клиента?": "Цель бота, список кнопок, какие данные собирать и кому отправлять заявки.",
    "Можно ли доработки?": "Да, можно добавлять новые разделы, роли, таблицы, интеграции и сценарии.",
}


def init_db() -> None:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            user_id INTEGER,
            username TEXT,
            full_name TEXT,
            phone TEXT,
            city TEXT,
            service TEXT,
            description TEXT,
            photo_file_id TEXT
        )
        """
    )
    conn.commit()
    conn.close()


def save_request_to_db(data: dict, user_id: int, username: str | None) -> int:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO requests (
            created_at, user_id, username, full_name, phone, city, service, description, photo_file_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            user_id,
            username,
            data.get("name", ""),
            data.get("phone", ""),
            data.get("city", ""),
            data.get("service", ""),
            data.get("description", ""),
            data.get("photo_file_id", ""),
        ),
    )
    conn.commit()
    request_id = cur.lastrowid
    conn.close()
    return int(request_id)


def build_request_summary(data: dict, user) -> str:
    username = f"@{user.username}" if user.username else "нет username"
    return (
        "📥 Новая заявка\n\n"
        f"👤 Имя: {data.get('name', '-')}\n"
        f"📞 Телефон: {data.get('phone', '-')}\n"
        f"🏙 Город: {data.get('city', '-')}\n"
        f"🛠 Услуга: {data.get('service', '-')}\n"
        f"📝 Описание: {data.get('description', '-')}\n"
        f"🆔 User ID: {user.id}\n"
        f"🔗 Username: {username}"
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        await update.message.reply_text(
            "Привет! Я бот Berik.\n\n"
            "Я могу показать услуги, ответить на частые вопросы и принять заявку.",
            reply_markup=MAIN_MENU,
        )


async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        await update.message.reply_text("Главное меню:", reply_markup=MAIN_MENU)


async def about(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        await update.message.reply_text(ABOUT_TEXT, reply_markup=MAIN_MENU)


async def services(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        await update.message.reply_text(SERVICES_TEXT, reply_markup=SERVICE_MENU)


async def price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        await update.message.reply_text(PRICE_TEXT, reply_markup=MAIN_MENU)


async def faq(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        await update.message.reply_text("❓ Выбери вопрос или вернись в меню.", reply_markup=FAQ_MENU)


async def manager(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        await update.message.reply_text(
            "📞 Связаться с менеджером:\n\nTelegram: @akhmeeedov",
            reply_markup=MAIN_MENU,
        )


async def answer_faq(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        answer = FAQ_ANSWERS.get(update.message.text)
        if answer:
            await update.message.reply_text(answer, reply_markup=FAQ_MENU)


async def start_request(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["request_form"] = {}
    if update.message:
        await update.message.reply_text(
            "📝 Начинаем оформление заявки.\n\nВведите ваше имя:",
            reply_markup=ReplyKeyboardMarkup([["⬅️ Отмена"]], resize_keyboard=True),
        )
    return NAME


async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text or "").strip()
    if text == "⬅️ Отмена":
        return await cancel(update, context)
    context.user_data["request_form"]["name"] = text
    await update.message.reply_text(
        "Теперь отправьте номер телефона текстом или кнопкой ниже.",
        reply_markup=PHONE_MENU,
    )
    return PHONE


async def get_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == "⬅️ Отмена":
        return await cancel(update, context)

    if update.message.contact:
        phone = update.message.contact.phone_number
    else:
        phone = (update.message.text or "").strip()

    context.user_data["request_form"]["phone"] = phone
    await update.message.reply_text(
        "Укажите ваш город:",
        reply_markup=ReplyKeyboardMarkup([["⬅️ Отмена"]], resize_keyboard=True),
    )
    return CITY


async def get_city(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text or "").strip()
    if text == "⬅️ Отмена":
        return await cancel(update, context)
    context.user_data["request_form"]["city"] = text
    await update.message.reply_text(
        "Выберите интересующую услугу:",
        reply_markup=ReplyKeyboardMarkup(
            [
                ["Консультация", "Разработка Telegram-бота"],
                ["Автоматизация заявок", "Техподдержка"],
                ["⬅️ Отмена"],
            ],
            resize_keyboard=True,
        ),
    )
    return SERVICE


async def get_service(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text or "").strip()
    if text == "⬅️ Отмена":
        return await cancel(update, context)
    context.user_data["request_form"]["service"] = text
    await update.message.reply_text(
        "Кратко опишите ваш запрос:",
        reply_markup=ReplyKeyboardMarkup([["⬅️ Отмена"]], resize_keyboard=True),
    )
    return DESCRIPTION


async def get_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text or "").strip()
    if text == "⬅️ Отмена":
        return await cancel(update, context)
    context.user_data["request_form"]["description"] = text
    await update.message.reply_text(
        "Если хотите, отправьте фото.\nИли нажмите «Пропустить».",
        reply_markup=YES_NO_SKIP_MENU,
    )
    return PHOTO


async def get_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text or "").strip()
    if text == "⬅️ Отмена":
        return await cancel(update, context)

    if text == "Пропустить":
        context.user_data["request_form"]["photo_file_id"] = ""
    elif update.message.photo:
        context.user_data["request_form"]["photo_file_id"] = update.message.photo[-1].file_id
    else:
        await update.message.reply_text(
            "Пожалуйста, отправьте фото или нажмите «Пропустить».",
            reply_markup=YES_NO_SKIP_MENU,
        )
        return PHOTO

    data = context.user_data["request_form"]
    summary = (
        "Проверьте заявку:\n\n"
        f"👤 Имя: {data.get('name')}\n"
        f"📞 Телефон: {data.get('phone')}\n"
        f"🏙 Город: {data.get('city')}\n"
        f"🛠 Услуга: {data.get('service')}\n"
        f"📝 Описание: {data.get('description')}\n"
        f"🖼 Фото: {'да' if data.get('photo_file_id') else 'нет'}"
    )
    await update.message.reply_text(summary, reply_markup=CONFIRM_MENU)
    return CONFIRM


async def confirm_request(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text or "").strip()

    if text == "⬅️ Отмена":
        return await cancel(update, context)

    if text == "✏️ Заполнить заново":
        context.user_data["request_form"] = {}
        await update.message.reply_text(
            "Хорошо, начнём заново.\nВведите ваше имя:",
            reply_markup=ReplyKeyboardMarkup([["⬅️ Отмена"]], resize_keyboard=True),
        )
        return NAME

    if text != "✅ Подтвердить":
        await update.message.reply_text(
            "Пожалуйста, выберите один из вариантов.",
            reply_markup=CONFIRM_MENU,
        )
        return CONFIRM

    data = context.user_data.get("request_form", {})
    user = update.effective_user
    request_id = save_request_to_db(data, user.id, user.username)
    admin_text = build_request_summary(data, user) + f"\n🗂 ID заявки: {request_id}"

    if data.get("photo_file_id"):
        await context.bot.send_photo(
            chat_id=ADMIN_CHAT_ID,
            photo=data["photo_file_id"],
            caption=admin_text,
        )
    else:
        await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=admin_text)

    await update.message.reply_text(
        "✅ Заявка отправлена.\nСпасибо! Менеджер свяжется с вами.",
        reply_markup=MAIN_MENU,
    )

    context.user_data["request_form"] = {}
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["request_form"] = {}
    if update.message:
        await update.message.reply_text(
            "Действие отменено. Возвращаю вас в главное меню.",
            reply_markup=MAIN_MENU,
        )
    return ConversationHandler.END


async def fallback_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (update.message.text or "").strip()

    if text == "💼 Услуги":
        await services(update, context)
    elif text == "💰 Прайс":
        await price(update, context)
    elif text == "❓ FAQ":
        await faq(update, context)
    elif text == "📞 Связаться с менеджером":
        await manager(update, context)
    elif text == "ℹ️ О боте":
        await about(update, context)
    elif text == "⬅️ Назад в меню":
        await menu(update, context)
    elif text in FAQ_ANSWERS:
        await answer_faq(update, context)
    else:
        await update.message.reply_text("Выберите действие из меню.", reply_markup=MAIN_MENU)


def main() -> None:
    init_db()
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^📝 Оставить заявку$"), start_request),
            CommandHandler("request", start_request),
        ],
        states={
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
            PHONE: [
                MessageHandler(filters.CONTACT, get_phone),
                MessageHandler(filters.TEXT & ~filters.COMMAND, get_phone),
            ],
            CITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_city)],
            SERVICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_service)],
            DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_description)],
            PHOTO: [
                MessageHandler(filters.PHOTO, get_photo),
                MessageHandler(filters.TEXT & ~filters.COMMAND, get_photo),
            ],
            CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_request)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            MessageHandler(filters.Regex("^⬅️ Отмена$"), cancel),
        ],
        allow_reentry=True,
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu))
    app.add_handler(CommandHandler("about", about))
    app.add_handler(CommandHandler("services", services))
    app.add_handler(CommandHandler("price", price))
    app.add_handler(CommandHandler("faq", faq))
    app.add_handler(CommandHandler("manager", manager))
    app.add_handler(conv_handler)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, fallback_text))

    print("Berik bot started with webhook...")
    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=TELEGRAM_BOT_TOKEN,
        webhook_url=f"{WEBHOOK_URL}/{TELEGRAM_BOT_TOKEN}",
    )


if __name__ == "__main__":
    main()
