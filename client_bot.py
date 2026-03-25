import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import json
import os
import re
from datetime import datetime
import logging
import time
from functools import wraps
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import database

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ==================== КОНФИГУРАЦИЯ ====================
CLIENT_BOT_TOKEN = "8739515859:AAEA1dNXUvBfWE4QXl24WdI-fxQn-EdfMGQ"
ADMIN_BOT_TOKEN = "8638017870:AAHImosiS0sK6M0H7JeI3SAeZ8K2C0I_ooo"
ADMIN_USER_ID = 1245450175
# ====================================================

# Создаем админ-бота для отправки заявок
admin_bot = telebot.TeleBot(ADMIN_BOT_TOKEN)

# Инициализация базы данных
database.init_database()


def create_retry_session():
    """Создание сессии с повторными попытками"""
    session = requests.Session()
    retry_strategy = Retry(
        total=5,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
    )
    adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=100, pool_maxsize=100)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


# Создаем клиентского бота
bot = telebot.TeleBot(
    CLIENT_BOT_TOKEN,
    threaded=True
)

bot.session = create_retry_session()

# Хранилище данных пользователей
user_data = {}


class UserState:
    WAITING_FIO = 1
    WAITING_PASSPORT_SERIES = 2
    WAITING_PASSPORT_NUMBER = 3
    WAITING_PASSPART_ISSUED = 4
    WAITING_PASSPORT_DATE = 5
    WAITING_CONFIRMATION = 6


def retry_on_failure(max_retries=3, delay=2):
    """Декоратор для повторных попыток при ошибках"""

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_retries - 1:
                        raise
                    logger.warning(f"Ошибка при выполнении {func.__name__}, попытка {attempt + 1}: {e}")
                    time.sleep(delay * (attempt + 1))
            return None

        return wrapper

    return decorator


@retry_on_failure(max_retries=3)
def safe_send_message(chat_id, text, **kwargs):
    """Безопасная отправка сообщения с повторными попытками"""
    try:
        return bot.send_message(chat_id, text, **kwargs)
    except requests.exceptions.ReadTimeout:
        logger.error(f"Timeout при отправке сообщения в {chat_id}")
        return bot.send_message(chat_id, text, timeout=30, **kwargs)
    except Exception as e:
        logger.error(f"Ошибка при отправке сообщения: {e}")
        raise


@bot.message_handler(commands=['start'])
def start_command(message):
    user_id = message.from_user.id
    user_data[user_id] = {
        'state': UserState.WAITING_FIO,
        'passport': {}
    }

    welcome_text = """
🏛️ *ЮРИДИЧЕСКАЯ КОНСУЛЬТАЦИЯ*

Здравствуйте! Я помогу вам оформить заявку на получение юридической помощи.

*Для начала работы, пожалуйста, введите:*

📝 *Ваше полное ФИО* (Фамилия Имя Отчество)

_Например: Иванов Иван Иванович_
"""
    safe_send_message(
        message.chat.id,
        welcome_text,
        parse_mode='Markdown'
    )


@bot.message_handler(commands=['status'])
def check_status(message):
    """Проверка статуса заявок"""
    user_id = message.from_user.id
    apps = database.get_user_applications(user_id, limit=5)

    if not apps:
        safe_send_message(
            message.chat.id,
            "📭 *У вас нет активных заявок.*\n\nИспользуйте /start для создания новой.",
            parse_mode='Markdown'
        )
        return

    status_emoji = {
        'pending': '⏳',
        'processing': '🔄',
        'completed': '✅',
        'rejected': '❌'
    }

    status_text = {
        'pending': 'Ожидает обработки',
        'processing': 'В обработке',
        'completed': 'Выполнена',
        'rejected': 'Отклонена'
    }

    response = "*📋 ВАШИ ПОСЛЕДНИЕ ЗАЯВКИ:*\n\n"
    for app in apps:
        emoji = status_emoji.get(app['status'], '📄')
        response += f"{emoji} *Заявка #{app['id']}*\n"
        response += f"📅 Дата: {app['created_at'][:10]}\n"
        response += f"📊 Статус: {status_text.get(app['status'], app['status'])}\n"
        response += f"👤 ФИО: {app['fio']}\n\n"

    safe_send_message(message.chat.id, response, parse_mode='Markdown')


@bot.message_handler(func=lambda message: user_data.get(message.from_user.id, {}).get('state') == UserState.WAITING_FIO)
def get_fio(message):
    user_id = message.from_user.id
    fio = message.text.strip()

    # Валидация ФИО
    words = fio.split()
    if len(words) < 2:
        safe_send_message(
            message.chat.id,
            "❌ *Ошибка:* ФИО должно содержать минимум фамилию и имя.\n\n"
            "Пожалуйста, введите полное ФИО в формате: *Фамилия Имя Отчество*",
            parse_mode='Markdown'
        )
        return

    if not re.match(r'^[а-яА-Яa-zA-Z\s-]+$', fio):
        safe_send_message(
            message.chat.id,
            "❌ *Ошибка:* ФИО должно содержать только буквы, пробелы и дефисы.\n\n"
            "Попробуйте еще раз:",
            parse_mode='Markdown'
        )
        return

    user_data[user_id]['fio'] = fio
    user_data[user_id]['state'] = UserState.WAITING_PASSPORT_SERIES

    safe_send_message(
        message.chat.id,
        "📄 *Введите серию паспорта*\n\n"
        "Серия состоит из 4 цифр.\n"
        "_Например: 4512_",
        parse_mode='Markdown'
    )


@bot.message_handler(
    func=lambda message: user_data.get(message.from_user.id, {}).get('state') == UserState.WAITING_PASSPORT_SERIES)
def get_passport_series(message):
    user_id = message.from_user.id
    series = message.text.strip()

    if not re.match(r'^\d{4}$', series):
        safe_send_message(
            message.chat.id,
            "❌ *Ошибка:* Серия паспорта должна состоять из 4 цифр.\n\n"
            "Пожалуйста, введите серию еще раз:",
            parse_mode='Markdown'
        )
        return

    user_data[user_id]['passport']['series'] = series
    user_data[user_id]['state'] = UserState.WAITING_PASSPORT_NUMBER

    safe_send_message(
        message.chat.id,
        "🔢 *Введите номер паспорта*\n\n"
        "Номер состоит из 6 цифр.\n"
        "_Например: 345678_",
        parse_mode='Markdown'
    )


@bot.message_handler(
    func=lambda message: user_data.get(message.from_user.id, {}).get('state') == UserState.WAITING_PASSPORT_NUMBER)
def get_passport_number(message):
    user_id = message.from_user.id
    number = message.text.strip()

    if not re.match(r'^\d{6}$', number):
        safe_send_message(
            message.chat.id,
            "❌ *Ошибка:* Номер паспорта должен состоять из 6 цифр.\n\n"
            "Пожалуйста, введите номер еще раз:",
            parse_mode='Markdown'
        )
        return

    user_data[user_id]['passport']['number'] = number
    user_data[user_id]['state'] = UserState.WAITING_PASSPART_ISSUED

    safe_send_message(
        message.chat.id,
        "🏢 *Кем выдан паспорт?*\n\n"
        "Введите полное наименование органа, выдавшего паспорт.\n"
        "_Например: ОВД \"Тверской\" г. Москвы_",
        parse_mode='Markdown'
    )


@bot.message_handler(
    func=lambda message: user_data.get(message.from_user.id, {}).get('state') == UserState.WAITING_PASSPART_ISSUED)
def get_passport_issued(message):
    user_id = message.from_user.id
    issued_by = message.text.strip()

    if len(issued_by) < 5:
        safe_send_message(
            message.chat.id,
            "❌ *Ошибка:* Пожалуйста, укажите полное наименование органа.\n\n"
            "Попробуйте еще раз:",
            parse_mode='Markdown'
        )
        return

    user_data[user_id]['passport']['issued_by'] = issued_by
    user_data[user_id]['state'] = UserState.WAITING_PASSPORT_DATE

    safe_send_message(
        message.chat.id,
        "📅 *Дата выдачи паспорта*\n\n"
        "Введите дату в формате: *ДД.ММ.ГГГГ*\n"
        "_Например: 15.03.2010_",
        parse_mode='Markdown'
    )


@bot.message_handler(
    func=lambda message: user_data.get(message.from_user.id, {}).get('state') == UserState.WAITING_PASSPORT_DATE)
def get_passport_date(message):
    user_id = message.from_user.id
    issue_date = message.text.strip()

    if not re.match(r'^\d{2}\.\d{2}\.\d{4}$', issue_date):
        safe_send_message(
            message.chat.id,
            "❌ *Ошибка:* Неверный формат даты.\n\n"
            "Пожалуйста, используйте формат *ДД.ММ.ГГГГ*\n"
            "_Например: 15.03.2010_",
            parse_mode='Markdown'
        )
        return

    try:
        day, month, year = map(int, issue_date.split('.'))
        datetime(year, month, day)
    except ValueError:
        safe_send_message(
            message.chat.id,
            "❌ *Ошибка:* Указана несуществующая дата.\n\n"
            "Пожалуйста, введите корректную дату:",
            parse_mode='Markdown'
        )
        return

    user_data[user_id]['passport']['issue_date'] = issue_date
    user_data[user_id]['state'] = UserState.WAITING_CONFIRMATION

    show_confirmation(message.chat.id, user_id)


def show_confirmation(chat_id, user_id):
    data = user_data[user_id]

    confirmation_text = f"""
*📋 ПРОВЕРЬТЕ ВВЕДЕННЫЕ ДАННЫЕ*

*👤 ФИО:* 
{data['fio']}

*🪪 ПАСПОРТНЫЕ ДАННЫЕ:*
• *Серия:* {data['passport']['series']}
• *Номер:* {data['passport']['number']}
• *Кем выдан:* {data['passport']['issued_by']}
• *Дата выдачи:* {data['passport']['issue_date']}

---
✅ *Все данные верны?*
"""

    markup = InlineKeyboardMarkup()
    markup.row_width = 2
    markup.add(
        InlineKeyboardButton("✅ Да, отправить", callback_data="confirm_yes"),
        InlineKeyboardButton("❌ Нет, начать сначала", callback_data="confirm_no"),
        InlineKeyboardButton("🔄 Изменить ФИО", callback_data="edit_fio"),
        InlineKeyboardButton("📝 Изменить паспорт", callback_data="edit_passport")
    )

    safe_send_message(
        chat_id,
        confirmation_text,
        parse_mode='Markdown',
        reply_markup=markup
    )


@bot.callback_query_handler(func=lambda call: True)
def handle_confirmation(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id

    if user_id not in user_data:
        safe_send_message(chat_id, "❌ Сессия истекла. Используйте /start для начала.")
        return

    if call.data == "confirm_yes":
        # Формируем заявку
        application = {
            'user_id': user_id,
            'username': call.from_user.username or 'не указан',
            'full_name': f"{call.from_user.first_name} {call.from_user.last_name or ''}".strip(),
            'fio': user_data[user_id]['fio'],
            'passport': user_data[user_id]['passport'],
            'date': datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
            'timestamp': datetime.now().timestamp()
        }

        try:
            # Сохраняем в базу данных
            app_id = database.save_application(application)
            logger.info(f"Заявка #{app_id} сохранена в БД")

            # Отправляем уведомление админу
            send_to_admin(application, app_id)

            # Сохраняем локально для резерва
            save_application_locally(application)

            safe_send_message(
                chat_id,
                f"✅ *ЗАЯВКА #{app_id} УСПЕШНО ОТПРАВЛЕНА!*\n\n"
                "Спасибо за обращение. Наш специалист свяжется с вами в ближайшее время.\n\n"
                "Вы можете проверить статус заявки командой /status",
                parse_mode='Markdown'
            )

        except Exception as e:
            logger.error(f"Ошибка при сохранении заявки: {e}")
            safe_send_message(
                chat_id,
                "❌ *Ошибка при отправке заявки.*\n\n"
                "Пожалуйста, попробуйте позже или обратитесь к администратору.",
                parse_mode='Markdown'
            )

        # Очищаем данные пользователя
        del user_data[user_id]

    elif call.data == "confirm_no":
        safe_send_message(
            chat_id,
            "🔄 *Давайте начнем заново.*\n\n"
            "Введите ваше полное ФИО:",
            parse_mode='Markdown'
        )
        user_data[user_id] = {'state': UserState.WAITING_FIO, 'passport': {}}

    elif call.data == "edit_fio":
        safe_send_message(
            chat_id,
            "✏️ *Введите новое ФИО:*\n\n"
            "_Формат: Фамилия Имя Отчество_",
            parse_mode='Markdown'
        )
        user_data[user_id]['state'] = UserState.WAITING_FIO

    elif call.data == "edit_passport":
        safe_send_message(
            chat_id,
            "✏️ *Давайте изменим паспортные данные.*\n\n"
            "Введите *серию паспорта* (4 цифры):",
            parse_mode='Markdown'
        )
        user_data[user_id]['state'] = UserState.WAITING_PASSPORT_SERIES
        user_data[user_id]['passport'] = {}

    try:
        bot.answer_callback_query(call.id)
    except Exception as e:
        logger.error(f"Ошибка при ответе на callback: {e}")


def send_to_admin(application, app_id):
    """Отправка заявки в админ-бот"""
    message_text = f"""
🆕 *НОВАЯ ЗАЯВКА #{app_id}*

*📱 ИНФОРМАЦИЯ О КЛИЕНТЕ:*
• *ID:* `{application['user_id']}`
• *Username:* @{application['username']}
• *Имя:* {application['full_name']}

*👤 ЛИЧНЫЕ ДАННЫЕ:*
• *ФИО:* {application['fio']}

*🪪 ПАСПОРТНЫЕ ДАННЫЕ:*
• *Серия:* {application['passport']['series']}
• *Номер:* {application['passport']['number']}
• *Кем выдан:* {application['passport']['issued_by']}
• *Дата выдачи:* {application['passport']['issue_date']}

*⏰ ДАТА ЗАЯВКИ:* 
{application['date']}

---
*📌 Статус:* Ожидает обработки
*🔗 ID в системе:* {app_id}
"""

    try:
        # Отправляем админу
        admin_bot.send_message(
            ADMIN_USER_ID,
            message_text,
            parse_mode='Markdown',
            timeout=30
        )
        logger.info(f"Уведомление о заявке #{app_id} отправлено админу")
    except Exception as e:
        logger.error(f"Ошибка отправки уведомления админу: {e}")
        # Сохраняем в файл для ручной отправки
        save_failed_application(application, app_id)


def save_failed_application(application, app_id):
    """Сохранение заявки, которую не удалось отправить админу"""
    filename = "failed_applications.json"
    try:
        if os.path.exists(filename):
            with open(filename, 'r', encoding='utf-8') as f:
                apps = json.load(f)
        else:
            apps = []

        apps.append({
            'app_id': app_id,
            'application': application,
            'failed_time': datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        })

        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(apps, f, ensure_ascii=False, indent=2)

        logger.warning(f"Заявка #{app_id} сохранена в {filename}")
    except Exception as e:
        logger.error(f"Ошибка сохранения неудачной заявки: {e}")


def save_application_locally(application):
    """Сохранение заявки в локальный JSON файл для резерва"""
    filename = "applications_backup.json"
    try:
        if os.path.exists(filename):
            with open(filename, 'r', encoding='utf-8') as f:
                apps = json.load(f)
        else:
            apps = []

        apps.append(application)

        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(apps, f, ensure_ascii=False, indent=2)

        logger.info(f"Заявка сохранена в {filename}")
    except Exception as e:
        logger.error(f"Ошибка сохранения заявки: {e}")


@bot.message_handler(commands=['help'])
def help_command(message):
    help_text = """
*📚 ДОСТУПНЫЕ КОМАНДЫ:*

/start - Начать оформление заявки
/status - Проверить статус заявки
/help - Показать это сообщение
/cancel - Отменить оформление заявки

---
*📝 ИНСТРУКЦИЯ:*
1. Введите свои данные по запросу бота
2. Проверьте правильность введенной информации
3. Подтвердите отправку заявки
4. Отслеживайте статус командой /status

*🕒 Время обработки:* до 30 минут

---
*📞 Контакты:* 
При возникновении вопросов обращайтесь к администратору.
"""
    safe_send_message(
        message.chat.id,
        help_text,
        parse_mode='Markdown'
    )


@bot.message_handler(commands=['cancel'])
def cancel_command(message):
    user_id = message.from_user.id
    if user_id in user_data:
        del user_data[user_id]
        safe_send_message(
            message.chat.id,
            "❌ *Оформление заявки отменено.*\n\n"
            "Если передумаете, используйте команду /start",
            parse_mode='Markdown'
        )
    else:
        safe_send_message(
            message.chat.id,
            "ℹ️ У вас нет активных заявок.\n\n"
            "Используйте /start для создания новой",
            parse_mode='Markdown'
        )


if __name__ == "__main__":
    logger.info("Клиентский бот для сбора заявок запущен...")
    logger.info("Пытаемся подключиться к Telegram API...")

    # Проверка подключения клиентского бота
    max_attempts = 5
    for attempt in range(max_attempts):
        try:
            bot_info = bot.get_me()
            logger.info(f"Клиентский бот успешно запущен: @{bot_info.username}")
            break
        except Exception as e:
            logger.error(f"Попытка {attempt + 1}/{max_attempts} не удалась: {e}")
            if attempt < max_attempts - 1:
                wait_time = (attempt + 1) * 5
                logger.info(f"Повторная попытка через {wait_time} секунд...")
                time.sleep(wait_time)
            else:
                logger.critical("Не удалось подключиться к Telegram API после всех попыток")
                exit(1)

    # Проверка подключения админ-бота
    try:
        admin_bot_info = admin_bot.get_me()
        logger.info(f"Админ-бот успешно подключен: @{admin_bot_info.username}")
    except Exception as e:
        logger.warning(f"Не удалось подключить админ-бота для уведомлений: {e}")

    # Запускаем клиентского бота
    try:
        bot.infinity_polling(
            timeout=30,
            long_polling_timeout=30,
            skip_pending=True
        )
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")