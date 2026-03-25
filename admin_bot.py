import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import json
import os
from datetime import datetime
import database

# Токен бота-админа
ADMIN_BOT_TOKEN = "8638017870:AAHImosiS0sK6M0H7JeI3SAeZ8K2C0I_ooo"
ADMIN_USER_ID = 1245450175  # Ваш ID

bot = telebot.TeleBot(ADMIN_BOT_TOKEN)

# Статусы заявок
STATUSES = {
    'pending': '⏳ Ожидает обработки',
    'processing': '🔄 В обработке',
    'completed': '✅ Завершена',
    'rejected': '❌ Отклонена'
}

# Инициализация базы данных
database.init_database()


@bot.message_handler(commands=['start'])
def start_command(message):
    if message.from_user.id != ADMIN_USER_ID:
        bot.send_message(message.chat.id, "❌ У вас нет доступа к этому боту.")
        return

    welcome_text = """
🔐 *Панель администратора*

*Доступные команды:*
/applications - Показать все заявки
/pending - Показать ожидающие заявки
/processing - Показать в обработке
/completed - Показать завершенные
/rejected - Показать отклоненные
/search [ID] - Найти заявку по ID
/stats - Статистика заявок
/status [ID] - Изменить статус заявки
/note [ID] [текст] - Добавить заметку
"""
    bot.send_message(message.chat.id, welcome_text, parse_mode='Markdown')


@bot.message_handler(commands=['applications'])
def show_all_applications(message):
    if message.from_user.id != ADMIN_USER_ID:
        return

    apps = database.get_all_applications(limit=20)

    if not apps:
        bot.send_message(message.chat.id, "📭 Нет заявок")
        return

    # Создаем клавиатуру с кнопками
    markup = InlineKeyboardMarkup()
    markup.row_width = 2

    for app in apps[:10]:  # Показываем последние 10
        status_emoji = {
            'pending': '⏳',
            'processing': '🔄',
            'completed': '✅',
            'rejected': '❌'
        }.get(app['status'], '📄')

        button_text = f"{status_emoji} #{app['id']} - {app['fio'][:20]} - {app['created_at'][:10]}"
        markup.add(InlineKeyboardButton(button_text, callback_data=f"view_{app['id']}"))

    bot.send_message(message.chat.id,
                     f"📋 *Всего заявок:* {len(apps)}\n\nВыберите заявку для просмотра:",
                     parse_mode='Markdown',
                     reply_markup=markup)


@bot.message_handler(commands=['pending'])
def show_pending(message):
    show_apps_by_status(message, 'pending')


@bot.message_handler(commands=['processing'])
def show_processing(message):
    show_apps_by_status(message, 'processing')


@bot.message_handler(commands=['completed'])
def show_completed(message):
    show_apps_by_status(message, 'completed')


@bot.message_handler(commands=['rejected'])
def show_rejected(message):
    show_apps_by_status(message, 'rejected')


def show_apps_by_status(message, status):
    if message.from_user.id != ADMIN_USER_ID:
        return

    apps = database.get_all_applications(status=status, limit=20)

    if not apps:
        bot.send_message(message.chat.id, f"📭 Нет заявок со статусом {STATUSES[status]}")
        return

    markup = InlineKeyboardMarkup()
    for app in apps[:10]:
        button_text = f"#{app['id']} - {app['fio'][:20]} - {app['created_at'][:10]}"
        markup.add(InlineKeyboardButton(button_text, callback_data=f"view_{app['id']}"))

    bot.send_message(message.chat.id,
                     f"📋 *{STATUSES[status]}:* {len(apps)} заявок",
                     parse_mode='Markdown',
                     reply_markup=markup)


@bot.callback_query_handler(func=lambda call: call.data.startswith('view_'))
def view_application(call):
    if call.from_user.id != ADMIN_USER_ID:
        return

    app_id = int(call.data.split('_')[1])
    app = database.get_application(app_id)

    if not app:
        bot.send_message(call.message.chat.id, "❌ Заявка не найдена")
        return

    # Получаем историю и заметки
    history = database.get_application_history(app_id)
    notes = database.get_application_notes(app_id)

    # Формируем сообщение
    status_emoji = {
        'pending': '⏳',
        'processing': '🔄',
        'completed': '✅',
        'rejected': '❌'
    }.get(app['status'], '📄')

    message_text = f"""
{status_emoji} *ЗАЯВКА #{app_id}* {status_emoji}

*📱 ИНФОРМАЦИЯ О КЛИЕНТЕ:*
• *ID:* `{app['user_id']}`
• *Username:* @{app['username'] or 'не указан'}
• *Имя:* {app['full_name']}

*👤 ЛИЧНЫЕ ДАННЫЕ:*
• *ФИО:* {app['fio']}

*🪪 ПАСПОРТНЫЕ ДАННЫЕ:*
• *Серия:* {app['passport_series']}
• *Номер:* {app['passport_number']}
• *Кем выдан:* {app['passport_issued_by']}
• *Дата выдачи:* {app['passport_issue_date']}

*📊 СТАТУС:* {STATUSES.get(app['status'], app['status'])}
*📅 СОЗДАНА:* {app['created_at']}
*🔄 ОБНОВЛЕНА:* {app['updated_at']}

*📝 ПОСЛЕДНИЕ ДЕЙСТВИЯ:*
"""
    if history:
        for h in history[:3]:
            message_text += f"\n• {h['created_at'][:16]} - {STATUSES.get(h['new_status'], h['new_status'])}"
            if h['comment']:
                message_text += f" ({h['comment']})"

    if notes:
        message_text += f"\n\n*📌 ЗАМЕТКИ:*"
        for note in notes[:3]:
            message_text += f"\n• {note['created_at'][:16]}: {note['note']}"

    markup = InlineKeyboardMarkup()
    markup.row_width = 2

    # Кнопки для изменения статуса
    status_buttons = []
    for status_key in ['processing', 'completed', 'rejected']:
        if app['status'] != status_key:
            status_buttons.append(InlineKeyboardButton(
                STATUSES[status_key],
                callback_data=f"status_{app_id}_{status_key}"
            ))

    if status_buttons:
        for btn in status_buttons:
            markup.add(btn)

    markup.add(
        InlineKeyboardButton("📝 Добавить заметку", callback_data=f"note_{app_id}"),
        InlineKeyboardButton("📜 Полная история", callback_data=f"history_{app_id}"),
        InlineKeyboardButton("🔙 Назад к списку", callback_data="back_to_list")
    )

    bot.edit_message_text(
        message_text,
        call.message.chat.id,
        call.message.message_id,
        parse_mode='Markdown',
        reply_markup=markup
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith('status_'))
def change_status(call):
    if call.from_user.id != ADMIN_USER_ID:
        return

    _, app_id, new_status = call.data.split('_')
    app_id = int(app_id)

    # Запрашиваем комментарий
    msg = bot.send_message(call.message.chat.id,
                           f"Введите комментарий к изменению статуса (или /skip для пропуска):")
    bot.register_next_step_handler(msg, process_status_comment, app_id, new_status, call.message)


def process_status_comment(message, app_id, new_status, original_message):
    if message.from_user.id != ADMIN_USER_ID:
        return

    comment = None
    if message.text != "/skip":
        comment = message.text

    # Обновляем статус
    success = database.update_application_status(
        app_id,
        new_status,
        comment=comment,
        changed_by=f"admin_{message.from_user.id}"
    )

    if success:
        # Отправляем уведомление пользователю
        app = database.get_application(app_id)
        if app:
            notify_user(app, new_status)

        bot.send_message(message.chat.id,
                         f"✅ Статус заявки #{app_id} изменен на {STATUSES[new_status]}")

        # Обновляем просмотр заявки
        view_application_callback(original_message, app_id)
    else:
        bot.send_message(message.chat.id, f"❌ Ошибка при изменении статуса")


def view_application_callback(message, app_id):
    """Вспомогательная функция для обновления просмотра"""
    app = database.get_application(app_id)
    if not app:
        bot.send_message(message.chat.id, "❌ Заявка не найдена")
        return

    history = database.get_application_history(app_id)
    notes = database.get_application_notes(app_id)

    status_emoji = {
        'pending': '⏳',
        'processing': '🔄',
        'completed': '✅',
        'rejected': '❌'
    }.get(app['status'], '📄')

    message_text = f"""
{status_emoji} *ЗАЯВКА #{app_id}* {status_emoji}

*📱 ИНФОРМАЦИЯ О КЛИЕНТЕ:*
• *ID:* `{app['user_id']}`
• *Username:* @{app['username'] or 'не указан'}
• *Имя:* {app['full_name']}

*👤 ЛИЧНЫЕ ДАННЫЕ:*
• *ФИО:* {app['fio']}

*🪪 ПАСПОРТНЫЕ ДАННЫЕ:*
• *Серия:* {app['passport_series']}
• *Номер:* {app['passport_number']}
• *Кем выдан:* {app['passport_issued_by']}
• *Дата выдачи:* {app['passport_issue_date']}

*📊 СТАТУС:* {STATUSES.get(app['status'], app['status'])}
*📅 СОЗДАНА:* {app['created_at']}
*🔄 ОБНОВЛЕНА:* {app['updated_at']}
"""

    markup = InlineKeyboardMarkup()
    markup.row_width = 2

    status_buttons = []
    for status_key in ['processing', 'completed', 'rejected']:
        if app['status'] != status_key:
            status_buttons.append(InlineKeyboardButton(
                STATUSES[status_key],
                callback_data=f"status_{app_id}_{status_key}"
            ))

    if status_buttons:
        for btn in status_buttons:
            markup.add(btn)

    markup.add(
        InlineKeyboardButton("📝 Добавить заметку", callback_data=f"note_{app_id}"),
        InlineKeyboardButton("📜 Полная история", callback_data=f"history_{app_id}"),
        InlineKeyboardButton("🔙 Назад к списку", callback_data="back_to_list")
    )

    bot.edit_message_text(
        message_text,
        message.chat.id,
        message.message_id,
        parse_mode='Markdown',
        reply_markup=markup
    )


def notify_user(app, new_status):
    """Отправка уведомления пользователю через клиентский бот"""
    # Здесь нужно отправить сообщение пользователю через клиентский бот
    # Для этого нужно использовать токен клиентского бота
    client_bot = telebot.TeleBot("8739515859:AAEA1dNXUvBfWE4QXl24WdI-fxQn-EdfMGQ")

    status_messages = {
        'processing': "🔄 *Ваша заявка принята в обработку!*\n\nСпециалист приступил к рассмотрению вашего обращения.",
        'completed': "✅ *Ваша заявка выполнена!*\n\nСпасибо за обращение. Если остались вопросы, вы можете создать новую заявку.",
        'rejected': "❌ *Ваша заявка отклонена.*\n\nЕсли у вас есть вопросы, пожалуйста, свяжитесь с администратором."
    }

    if new_status in status_messages:
        try:
            client_bot.send_message(
                app['user_id'],
                status_messages[new_status],
                parse_mode='Markdown'
            )
            database.logger.info(f"Уведомление отправлено пользователю {app['user_id']}")
        except Exception as e:
            database.logger.error(f"Ошибка отправки уведомления: {e}")


@bot.callback_query_handler(func=lambda call: call.data.startswith('note_'))
def add_note(call):
    if call.from_user.id != ADMIN_USER_ID:
        return

    app_id = int(call.data.split('_')[1])

    msg = bot.send_message(call.message.chat.id,
                           f"Введите заметку для заявки #{app_id}:")
    bot.register_next_step_handler(msg, process_note, app_id, call.message)


def process_note(message, app_id, original_message):
    if message.from_user.id != ADMIN_USER_ID:
        return

    note = message.text
    database.add_note_to_application(app_id, note, f"admin_{message.from_user.id}")

    bot.send_message(message.chat.id, f"✅ Заметка добавлена к заявке #{app_id}")

    # Обновляем просмотр
    view_application_callback(original_message, app_id)


@bot.callback_query_handler(func=lambda call: call.data.startswith('history_'))
def show_history(call):
    if call.from_user.id != ADMIN_USER_ID:
        return

    app_id = int(call.data.split('_')[1])
    history = database.get_application_history(app_id)

    if not history:
        bot.send_message(call.message.chat.id, "📭 История пуста")
        return

    history_text = f"*📜 История заявки #{app_id}:*\n\n"
    for h in history:
        history_text += f"• {h['created_at'][:16]} - {STATUSES.get(h['new_status'], h['new_status'])}"
        if h['comment']:
            history_text += f"\n  Комментарий: {h['comment']}"
        history_text += "\n\n"

    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🔙 Назад к заявке", callback_data=f"view_{app_id}"))

    bot.edit_message_text(
        history_text,
        call.message.chat.id,
        call.message.message_id,
        parse_mode='Markdown',
        reply_markup=markup
    )


@bot.callback_query_handler(func=lambda call: call.data == "back_to_list")
def back_to_list(call):
    if call.from_user.id != ADMIN_USER_ID:
        return

    show_all_applications(call.message)


@bot.message_handler(commands=['search'])
def search_application(message):
    if message.from_user.id != ADMIN_USER_ID:
        return

    try:
        _, app_id = message.text.split()
        app_id = int(app_id)

        app = database.get_application(app_id)
        if app:
            # Создаем фейковое сообщение для просмотра
            class FakeMessage:
                pass

            fake_msg = FakeMessage()
            fake_msg.chat = message.chat
            fake_msg.message_id = message.message_id + 1

            view_application_callback(fake_msg, app_id)
        else:
            bot.send_message(message.chat.id, f"❌ Заявка #{app_id} не найдена")
    except:
        bot.send_message(message.chat.id, "❌ Использование: /search [ID заявки]")


@bot.message_handler(commands=['stats'])
def show_stats(message):
    if message.from_user.id != ADMIN_USER_ID:
        return

    stats = database.get_statistics()

    stats_text = f"""
*📊 СТАТИСТИКА ЗАЯВОК*

*Общая статистика:*
• Всего заявок: {stats['total']}
• За сегодня: {stats['today']}

*По статусам:*
• ⏳ Ожидает: {stats['pending']}
• 🔄 В обработке: {stats['processing']}
• ✅ Завершено: {stats['completed']}
• ❌ Отклонено: {stats['rejected']}

---
*Команды для управления:*
/pending - просмотр ожидающих
/status [ID] [статус] - изменить статус
/note [ID] [текст] - добавить заметку
"""
    bot.send_message(message.chat.id, stats_text, parse_mode='Markdown')


@bot.message_handler(commands=['status'])
def change_status_command(message):
    if message.from_user.id != ADMIN_USER_ID:
        return

    try:
        parts = message.text.split()
        if len(parts) < 3:
            bot.send_message(message.chat.id,
                             "❌ Использование: /status [ID] [pending|processing|completed|rejected] [комментарий]")
            return

        app_id = int(parts[1])
        new_status = parts[2]
        comment = ' '.join(parts[3:]) if len(parts) > 3 else None

        if new_status not in STATUSES:
            bot.send_message(message.chat.id,
                             f"❌ Неверный статус. Доступные: {', '.join(STATUSES.keys())}")
            return

        success = database.update_application_status(
            app_id, new_status, comment=comment, changed_by=f"admin_{message.from_user.id}"
        )

        if success:
            app = database.get_application(app_id)
            if app:
                notify_user(app, new_status)

            bot.send_message(message.chat.id,
                             f"✅ Статус заявки #{app_id} изменен на {STATUSES[new_status]}")
        else:
            bot.send_message(message.chat.id, f"❌ Заявка #{app_id} не найдена")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: {e}")


if __name__ == "__main__":
    print("Админ-бот запущен...")
    bot.infinity_polling()