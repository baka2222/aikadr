"""Optional Telegram notifications and approval bot using long polling."""

import json
import os
import time

import httpx

from .db import database, one
from .payments import review_payment


TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.getenv("TELEGRAM_ADMIN_CHAT_ID", "").strip()
ADMIN_IDS = {int(item.strip()) for item in os.getenv("TELEGRAM_ADMIN_IDS", "").split(",") if item.strip().isdigit()}


def bot_api(method, *, data=None, files=None, timeout=35):
    if not TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is empty")
    response = httpx.post(f"https://api.telegram.org/bot{TOKEN}/{method}", data=data, files=files, timeout=timeout)
    response.raise_for_status()
    result = response.json()
    if not result.get("ok"):
        raise RuntimeError(result.get("description", "Telegram error"))
    return result["result"]


def notify_payment(request_id, email, plan, amount, receipt, mime, method_title=""):
    if not TOKEN or not CHAT_ID:
        return
    markup = {"inline_keyboard": [[
        {"text": "✓ Подтвердить", "callback_data": f"pay:approved:{request_id}"},
        {"text": "✕ Отклонить", "callback_data": f"pay:rejected:{request_id}"},
    ]]}
    bot_api("sendPhoto", data={
        "chat_id": CHAT_ID,
        "caption": f"Заявка на подписку\n{email}\nТариф: {plan}\nСпособ: {method_title}\nСумма: {amount} сом\nID: {request_id}\nСначала проверьте реальное поступление денег.",
        "reply_markup": json.dumps(markup, ensure_ascii=False),
    }, files={"photo": ("receipt.jpg", receipt, mime)})


def handle_callback(callback):
    callback_id = callback.get("id")
    user_id = callback.get("from", {}).get("id")
    chat_id = str(callback.get("message", {}).get("chat", {}).get("id", ""))
    parts = callback.get("data", "").split(":")
    if not callback_id or user_id not in ADMIN_IDS or chat_id != CHAT_ID or len(parts) != 3 or parts[0] != "pay":
        if callback_id:
            bot_api("answerCallbackQuery", data={"callback_query_id": callback_id, "text": "Нет доступа"})
        return
    _, decision, request_id = parts
    with database() as db:
        reviewer = one(db, "SELECT id FROM users WHERE role='superadmin' AND is_active=TRUE ORDER BY created_at LIMIT 1")
    if not reviewer:
        bot_api("answerCallbackQuery", data={"callback_query_id": callback_id, "text": "Нет супер-администратора"})
        return
    try:
        review_payment(request_id, decision, reviewer["id"], f"Обработано в Telegram пользователем {user_id}")
        bot_api("answerCallbackQuery", data={"callback_query_id": callback_id, "text": "Заявка обработана"})
        message = callback.get("message", {})
        bot_api("editMessageReplyMarkup", data={"chat_id": CHAT_ID, "message_id": message.get("message_id"),
                                                "reply_markup": json.dumps({"inline_keyboard": []})})
        bot_api("sendMessage", data={"chat_id": CHAT_ID, "text": f"Заявка {request_id}: {decision}"})
    except Exception as exc:
        bot_api("answerCallbackQuery", data={"callback_query_id": callback_id, "text": f"Ошибка: {str(exc)[:140]}", "show_alert": "true"})


def run_bot():
    if not TOKEN or not CHAT_ID or not ADMIN_IDS:
        raise RuntimeError("Set TELEGRAM_BOT_TOKEN, TELEGRAM_ADMIN_CHAT_ID and TELEGRAM_ADMIN_IDS")
    offset = 0
    while True:
        try:
            updates = bot_api("getUpdates", data={"timeout": 25, "offset": offset, "allowed_updates": '["callback_query"]'}, timeout=35)
            for update in updates:
                offset = update["update_id"] + 1
                if update.get("callback_query"):
                    handle_callback(update["callback_query"])
        except Exception as exc:
            print(f"Telegram polling error: {exc}", flush=True)
            time.sleep(5)


if __name__ == "__main__":
    run_bot()
