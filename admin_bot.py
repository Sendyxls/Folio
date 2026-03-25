import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import json
import os
from datetime import datetime

# Токен бота-админа
ADMIN_BOT_TOKEN = "8638017870:AAHImosiS0sK6M0H7JeI3SAeZ8K2C0I_ooo"
ADMIN_USER_ID = 1245450175  # Замените на реальный ID

bot = telebot.TeleBot(ADMIN_BOT_TOKEN)

# Хранилище заявок
applications = {}
next_id = 1

# Путь для сохранения заявок
DATA_FILE = "applications.json"


def load_applications():
    global applications, next_id
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            applications = data.get('applications', {})
            next_id = data.get('next_id', 1)


def save_applications():
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump({
            'applications': applications,
            'next_id': next_id
        }, f, ensure_ascii=False, indent=2)


# Загружаем данные при старте
load_applications()


@bot.message_handler(commands=['start'])
def start_command(message):
    if message.from_user.id != ADMIN_USER_ID:
        bot.send_message(message.chat.id, "❌ У вас нет доступа к этому боту.")
        return

    welcome_text = """
    🔐 *Панель администратора*

    *Доступные команды:*
    /applications - Показать все заявки
    /last - Показать последние 5 заявок
    /search [ID] - Найти заявку по ID
    /stats - Статистика заявок
    """
    bot.send_message(message.chat.id, welcome_text, parse_mode='Markdown')


@bot.message_handler(commands=['applications'])
def show_all_applications(message):
    if message.from_user.id != ADMIN_USER_ID:
        return

    if not applications:
        bot.send_message(message.chat.id, "📭 Нет новых заявок")
        return

    # Создаем клавиатуру с кнопками для навигации
    markup = InlineKeyboardMarkup()
    markup.row_width = 2

    # Добавляем кнопки для каждой заявки
    for app_id in sorted(applications.keys(), reverse=True)[:10]:  # Показываем последние 10
        app = applications[app_id]
        button_text = f"📄 Заявка #{app_id} - {app['date']}"
        markup.add(InlineKeyboardButton(button_text, callback_data=f"view_{app_id}"))

    if len(applications) > 10:
        markup.add(InlineKeyboardButton("📋 Все заявки в файле", callback_data="export_json"))

    bot.send_message(message.chat.id,
                     f"📋 *Всего заявок:* {len(applications)}\n\nВыберите заявку для просмотра:",
                     parse_mode='Markdown',
                     reply_markup=markup)


@bot.callback_query_handler(func=lambda call: call.data.startswith('view_'))
def view_application(call):
    if call.from_user.id != ADMIN_USER_ID:
        return

    app_id = int(call.data.split('_')[1])
    if app_id not in applications:
        bot.send_message(call.message.chat.id, "❌ Заявка не найдена")
        return

    app = applications[app_id]

    # Формируем сообщение с заявкой
    message_text = f"""
    *📋 ЗАЯВКА #{app_id}*\n
    *Информация о клиенте:*
    • ID Telegram: {app['user_id']}
    • Username: @{app['username'] or 'не указан'}
    • Имя в TG: {app['full_name']}

    *Личные данные:*
    • ФИО: {app['fio']}

    *Паспортные данные:*
    • Серия: {app['passport']['series']}
    • Номер: {app['passport']['number']}
    • Кем выдан: {app['passport']['issued_by']}
    • Дата выдачи: {app['passport']['issue_date']}

    *Дата заявки:* {app['date']}
    """

    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("🗑 Удалить заявку", callback_data=f"delete_{app_id}"),
        InlineKeyboardButton("📊 Назад к списку", callback_data="back_to_list")
    )

    bot.send_message(call.message.chat.id, message_text, parse_mode='Markdown', reply_markup=markup)


@bot.callback_query_handler(func=lambda call: call.data.startswith('delete_'))
def delete_application(call):
    if call.from_user.id != ADMIN_USER_ID:
        return

    app_id = int(call.data.split('_')[1])
    if app_id in applications:
        del applications[app_id]
        save_applications()
        bot.send_message(call.message.chat.id, f"✅ Заявка #{app_id} удалена")
    else:
        bot.send_message(call.message.chat.id, "❌ Заявка не найдена")


@bot.message_handler(commands=['last'])
def show_last_applications(message):
    if message.from_user.id != ADMIN_USER_ID:
        return

    if not applications:
        bot.send_message(message.chat.id, "📭 Нет заявок")
        return

    last_apps = sorted(applications.keys(), reverse=True)[:5]

    response = "*📋 Последние 5 заявок:*\n\n"
    for app_id in last_apps:
        app = applications[app_id]
        response += f"*Заявка #{app_id}*\n"
        response += f"• ФИО: {app['fio']}\n"
        response += f"• Дата: {app['date']}\n"
        response += f"• ID: {app['user_id']}\n\n"

    bot.send_message(message.chat.id, response, parse_mode='Markdown')


@bot.message_handler(commands=['search'])
def search_application(message):
    if message.from_user.id != ADMIN_USER_ID:
        return

    try:
        _, app_id = message.text.split()
        app_id = int(app_id)

        if app_id in applications:
            app = applications[app_id]
            message_text = f"""
            *📋 ЗАЯВКА #{app_id}*\n
            *ФИО:* {app['fio']}
            *Паспорт:* {app['passport']['series']} {app['passport']['number']}
            *Дата:* {app['date']}
            """
            bot.send_message(message.chat.id, message_text, parse_mode='Markdown')
        else:
            bot.send_message(message.chat.id, f"❌ Заявка #{app_id} не найдена")

    except:
        bot.send_message(message.chat.id, "❌ Использование: /search [ID заявки]")


@bot.message_handler(commands=['stats'])
def show_stats(message):
    if message.from_user.id != ADMIN_USER_ID:
        return

    # Собираем статистику
    total = len(applications)
    today = datetime.now().strftime("%d.%m.%Y")

    # Считаем заявки за сегодня
    today_apps = sum(1 for app in applications.values()
                     if app['date'].startswith(today))

    stats_text = f"""
    *📊 Статистика заявок*\n
    • Всего заявок: {total}
    • За сегодня: {today_apps}
    • Последняя заявка: {max([app['date'] for app in applications.values()]) if applications else 'нет'}
    """

    bot.send_message(message.chat.id, stats_text, parse_mode='Markdown')


# Функция для получения заявок от клиентского бота
@bot.message_handler(func=lambda message: True)
def handle_incoming_application(message):
    """Обработка входящих заявок от клиентского бота"""
    global next_id

    if message.from_user.id != ADMIN_USER_ID:
        # Проверяем, что сообщение пришло от клиентского бота
        # (можно добавить дополнительную проверку)

        # Парсим сообщение и сохраняем как заявку
        # Здесь нужно реализовать парсинг сообщения от клиентского бота
        # Для простоты сохраняем текст как есть

        app_id = next_id
        applications[app_id] = {
            'id': app_id,
            'text': message.text,
            'date': datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
            'user_id': message.from_user.id
        }
        next_id += 1
        save_applications()

        # Отправляем уведомление админу
        bot.send_message(ADMIN_USER_ID,
                         f"🔔 Получена новая заявка #{app_id}!\n"
                         f"Используйте /applications для просмотра")


if __name__ == "__main__":
    print("Админ-бот запущен...")
    bot.infinity_polling()