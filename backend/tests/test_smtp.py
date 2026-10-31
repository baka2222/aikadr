"""Real SMTP roundtrip against local Mailpit only, using an isolated test DB."""
import os
import re
import sys
from pathlib import Path
from uuid import uuid4

import httpx
from fastapi.testclient import TestClient

test_url = os.environ.get("TEST_DATABASE_URL", "")
if not test_url.endswith("/kadr_test") or os.getenv("SMTP_HOST") != "mailpit":
    raise RuntimeError("Requires dedicated kadr_test and local Mailpit; never send real email from this test")
os.environ["DATABASE_URL"] = test_url
os.environ["APP_ENV"] = "development"
os.environ["SECURE_COOKIES"] = "false"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.main import app

email = f"smtp-{uuid4().hex}@aikadr.local"
with TestClient(app) as client:
    begin = client.post("/api/auth/register", json={"email": email, "full_name": "Проверка SMTP", "password": uuid4().hex})
    assert begin.status_code == 201, begin.text
    assert client.get("/api/auth/me").status_code == 401
    messages = httpx.get("http://mailpit:8025/api/v1/messages").json()["messages"]
    item = next(message for message in messages if any(recipient["Address"] == email for recipient in message["To"]))
    message = httpx.get(f"http://mailpit:8025/api/v1/message/{item['ID']}").json()
    code = re.search(r"Ваш код: (\d{6})", message["Text"]).group(1)
    assert "Добро пожаловать" in message["HTML"] and "Проверка SMTP" in message["HTML"]
    assert code in message["HTML"]
    verified = client.post("/api/auth/verify-email", json={"challenge_id": begin.json()["challenge_id"], "code": code})
    assert verified.status_code == 200, verified.text
    assert client.get("/api/auth/me").json()["email_verified"]
print("SMTP delivery, branded HTML/plain email, and mandatory-code registration: OK")
