import sqlite3
import json
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

DB_PATH = "/root/Folio/applications.db"


def init_database():
    """Инициализация базы данных"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Таблица заявок
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            username TEXT,
            full_name TEXT,
            fio TEXT NOT NULL,
            passport_series TEXT NOT NULL,
            passport_number TEXT NOT NULL,
            passport_issued_by TEXT NOT NULL,
            passport_issue_date TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Таблица истории статусов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS status_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            application_id INTEGER NOT NULL,
            old_status TEXT,
            new_status TEXT NOT NULL,
            comment TEXT,
            changed_by TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (application_id) REFERENCES applications(id)
        )
    ''')

    # Таблица для комментариев/заметок
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS application_notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            application_id INTEGER NOT NULL,
            note TEXT NOT NULL,
            created_by TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (application_id) REFERENCES applications(id)
        )
    ''')

    conn.commit()
    conn.close()
    logger.info("База данных инициализирована")


def save_application(application):
    """Сохранение новой заявки в базу"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('''
        INSERT INTO applications (
            user_id, username, full_name, fio, 
            passport_series, passport_number, 
            passport_issued_by, passport_issue_date, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        application['user_id'],
        application['username'],
        application['full_name'],
        application['fio'],
        application['passport']['series'],
        application['passport']['number'],
        application['passport']['issued_by'],
        application['passport']['issue_date'],
        'pending'
    ))

    app_id = cursor.lastrowid

    # Добавляем в историю
    cursor.execute('''
        INSERT INTO status_history (application_id, old_status, new_status, comment, changed_by)
        VALUES (?, ?, ?, ?, ?)
    ''', (app_id, None, 'pending', 'Заявка создана', 'system'))

    conn.commit()
    conn.close()

    logger.info(f"Заявка #{app_id} сохранена в БД")
    return app_id


def get_application(app_id):
    """Получение заявки по ID"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute('SELECT * FROM applications WHERE id = ?', (app_id,))
    app = cursor.fetchone()

    conn.close()
    return dict(app) if app else None


def get_user_applications(user_id, limit=10):
    """Получение заявок пользователя"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute('''
        SELECT * FROM applications 
        WHERE user_id = ? 
        ORDER BY created_at DESC 
        LIMIT ?
    ''', (user_id, limit))

    apps = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return apps


def get_all_applications(status=None, limit=50):
    """Получение всех заявок с фильтром по статусу"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    if status:
        cursor.execute('''
            SELECT * FROM applications 
            WHERE status = ? 
            ORDER BY created_at DESC 
            LIMIT ?
        ''', (status, limit))
    else:
        cursor.execute('''
            SELECT * FROM applications 
            ORDER BY created_at DESC 
            LIMIT ?
        ''', (limit,))

    apps = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return apps


def update_application_status(app_id, new_status, comment=None, changed_by=None):
    """Обновление статуса заявки"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Получаем текущий статус
    cursor.execute('SELECT status FROM applications WHERE id = ?', (app_id,))
    result = cursor.fetchone()
    if not result:
        conn.close()
        return False

    old_status = result[0]

    # Обновляем статус
    cursor.execute('''
        UPDATE applications 
        SET status = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
    ''', (new_status, app_id))

    # Добавляем в историю
    cursor.execute('''
        INSERT INTO status_history (application_id, old_status, new_status, comment, changed_by)
        VALUES (?, ?, ?, ?, ?)
    ''', (app_id, old_status, new_status, comment, changed_by))

    conn.commit()
    conn.close()

    logger.info(f"Статус заявки #{app_id} изменен с {old_status} на {new_status}")
    return True


def add_note_to_application(app_id, note, created_by=None):
    """Добавление заметки к заявке"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('''
        INSERT INTO application_notes (application_id, note, created_by)
        VALUES (?, ?, ?)
    ''', (app_id, note, created_by))

    conn.commit()
    conn.close()
    logger.info(f"Заметка добавлена к заявке #{app_id}")


def get_application_history(app_id):
    """Получение истории статусов заявки"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute('''
        SELECT * FROM status_history 
        WHERE application_id = ? 
        ORDER BY created_at DESC
    ''', (app_id,))

    history = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return history


def get_application_notes(app_id):
    """Получение заметок по заявке"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute('''
        SELECT * FROM application_notes 
        WHERE application_id = ? 
        ORDER BY created_at DESC
    ''', (app_id,))

    notes = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return notes


def get_statistics():
    """Получение статистики по заявкам"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    stats = {}

    # Общее количество
    cursor.execute('SELECT COUNT(*) FROM applications')
    stats['total'] = cursor.fetchone()[0]

    # По статусам
    for status in ['pending', 'processing', 'completed', 'rejected']:
        cursor.execute('SELECT COUNT(*) FROM applications WHERE status = ?', (status,))
        stats[status] = cursor.fetchone()[0]

    # За сегодня
    cursor.execute('''
        SELECT COUNT(*) FROM applications 
        WHERE DATE(created_at) = DATE('now')
    ''')
    stats['today'] = cursor.fetchone()[0]

    conn.close()
    return stats