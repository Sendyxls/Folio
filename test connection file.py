import requests
import time


def test_telegram_api():
    urls = [
        "https://api.telegram.org",
        "https://api.telegram.org/bot",
        "https://core.telegram.org"
    ]

    for url in urls:
        try:
            response = requests.get(url, timeout=10)
            print(f"✅ {url} - Доступен (статус: {response.status_code})")
        except Exception as e:
            print(f"❌ {url} - Ошибка: {e}")


if __name__ == "__main__":
    print("Проверка подключения к Telegram API...")
    test_telegram_api()