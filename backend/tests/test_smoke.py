"""Integration checks against a dedicated PostgreSQL database ending in _test."""

import os
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from fastapi import HTTPException
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

test_url = os.environ.get("TEST_DATABASE_URL", "")
if not test_url.endswith("/kadr_test"):
    raise RuntimeError("Set TEST_DATABASE_URL to a dedicated /kadr_test database")
os.environ["DATABASE_URL"] = test_url
os.environ["APP_ENV"] = "development"
os.environ["SECURE_COOKIES"] = "false"
tempdir = tempfile.TemporaryDirectory()
os.environ["DATA_DIR"] = tempdir.name
os.environ["ADMIN_EMAIL"] = "admin-test@kadr.local"
os.environ["ADMIN_PASSWORD"] = "test-password-very-long"
os.environ["SESSION_SECRET"] = "test-secret-at-least-thirty-two-characters-long"

from app.db import database, execute, one
from app.main import app


class PlatformFlow(unittest.TestCase):
    def setUp(self):
        self.codes = {}
        self.mailer = patch("app.auth.send_code_email", side_effect=lambda email, name, code, purpose: self.codes.update({email: code}))
        self.mailer.start()
        self.addCleanup(self.mailer.stop)

    def authenticate(self, client, path, *, json):
        # Simulate the resend interval passing only in the isolated test database.
        with database() as db:
            execute(db, "UPDATE auth_challenges SET created_at=created_at-61 WHERE email=%s", (json["email"],))
        response = client.post(path, json=json)
        if path == "/api/admin/login" and response.status_code == 200:
            self.assertIn("kadr_session=", response.headers.get("set-cookie", ""))
            self.assertNotIn("challenge_id", response.json())
            self.assertNotIn(json["email"], self.codes)
            self.assertEqual(client.get("/api/admin/session").status_code, 200)
            return response
        if response.status_code in (200, 201):
            self.assertNotIn("set-cookie", response.headers)
            verified = client.post("/api/auth/verify-email", json={
                "challenge_id": response.json()["challenge_id"], "code": self.codes[json["email"]],
            })
            self.assertEqual(verified.status_code, 200, verified.text)
            self.assertTrue(verified.json()["email_verified"])
        return response

    @classmethod
    def tearDownClass(cls):
        tempdir.cleanup()

    def test_accounts_payment_video_and_revenue(self):
        with TestClient(app) as admin, TestClient(app) as author, TestClient(app) as viewer, TestClient(app) as stranger:
            self.assertEqual(admin.get("/api/health").status_code, 200)
            self.assertEqual(admin.get("/api/series").json(), [])
            self.assertEqual(admin.get("/api/plans").json(), [])
            self.assertEqual(admin.post("/api/admin/categories", json={"name": "Test"}).status_code, 401)
            with patch("app.main.issue_challenge", side_effect=AssertionError("staff login must not send email")):
                self.assertEqual(self.authenticate(admin, "/api/admin/login", json={"email": "admin-test@kadr.local", "password": "test-password-very-long"}).status_code, 200)
            self.assertEqual(admin.get("/api/admin/session").json()["role"], "superadmin")
            self.assertFalse(admin.get("/api/admin/session").json()["email_verified"])

            creator = admin.post("/api/admin/users", json={
                "full_name": "Автор Тест", "email": "author-test@example.com", "password": "author-pass-123", "role": "author",
            })
            self.assertEqual(creator.status_code, 201, creator.text)
            author_id = creator.json()["id"]
            self.assertEqual(self.authenticate(author, "/api/admin/login", json={"email": "author-test@example.com", "password": "author-pass-123"}).status_code, 200)
            self.assertEqual(author.post("/api/auth/login", json={"email": "author-test@example.com", "password": "author-pass-123"}).status_code, 403)
            self.assertEqual(self.authenticate(viewer, "/api/auth/register", json={
                "full_name": "Зритель Тест", "email": "viewer-test@example.com", "password": "viewer-pass-123",
            }).status_code, 201)
            self.assertEqual(self.authenticate(stranger, "/api/auth/register", json={
                "full_name": "Другой зритель", "email": "stranger-test@example.com", "password": "stranger-pass-123",
            }).status_code, 201)
            with TestClient(app) as visitor:
                denied = visitor.post("/api/admin/login", json={"email": "viewer-test@example.com", "password": "viewer-pass-123"})
                self.assertEqual(denied.status_code, 403)
                self.assertNotIn("set-cookie", denied.headers)
                self.assertEqual(visitor.get("/api/admin/session").status_code, 401)

            category_id = admin.get("/api/categories").json()[0]["id"]
            show = author.post("/api/admin/series", json={
                "title": "Тестовый сериал", "description": "История для теста", "category_id": category_id,
                "year": 2026, "rating": "12+", "is_published": True,
            })
            self.assertEqual(show.status_code, 201, show.text)
            show_id = show.json()["id"]
            self.assertEqual(show.json()["owner_id"], author_id)
            self.assertEqual(viewer.put(f"/api/admin/series/{show_id}", json={
                "title": "Нет", "description": "Нет", "category_id": category_id, "year": 2026,
            }).status_code, 403)
            episode = author.post(f"/api/admin/series/{show_id}/episodes", json={
                "season": 1, "number": 1, "title": "Пилот", "duration": "1 мин", "free_preview": False,
            })
            self.assertEqual(episode.status_code, 201, episode.text)
            episode_id = episode.json()["id"]
            self.assertEqual(author.post(f"/api/admin/series/{show_id}/episodes", json={
                "season": 1, "number": 2, "title": "Внешний платный", "video_url": "https://example.com/video.mp4",
                "free_preview": False,
            }).status_code, 422)
            video = b"\x00\x00\x00\x18ftypisom" + b"example-video-content" * 10
            uploaded = author.post(f"/api/admin/episodes/{episode_id}/video", files={"file": ("test.mp4", video, "video/mp4")})
            self.assertEqual(uploaded.status_code, 200, uploaded.text)
            with database() as db:
                asset = one(db, "SELECT * FROM videos WHERE episode_id=%s", (episode_id,))
                self.assertEqual(asset["uploaded_by"], author_id)
                self.assertEqual(asset["byte_size"], len(video))
                first_oid = asset["large_object_oid"]
            replaced = author.post(f"/api/admin/episodes/{episode_id}/video", files={"file": ("replacement.mp4", video, "video/mp4")})
            self.assertEqual(replaced.status_code, 200, replaced.text)
            self.assertEqual(author.get(f"/api/admin/episodes/{episode_id}/upload-info").json()["storage_used_bytes"], len(video))
            with database() as db:
                execute(db, "UPDATE users SET storage_quota_bytes=%s WHERE id=%s", (len(video) + 3, author_id))
            second_episode = author.post(f"/api/admin/series/{show_id}/episodes", json={
                "season": 1, "number": 3, "title": "Другая серия", "duration": "1 мин",
            }).json()["id"]
            self.assertEqual(author.post(f"/api/admin/episodes/{second_episode}/video", files={"file": ("test.mp4", video, "video/mp4")}).status_code, 413)
            self.assertEqual(author.post(f"/api/admin/episodes/{episode_id}/video", files={"file": ("test.mp4", video, "video/mp4")}).status_code, 200)
            self.assertEqual(admin.put(f"/api/admin/users/{author_id}", json={"full_name": "Автор Тест", "role": "author", "is_active": True, "storage_quota_gb": 1}).status_code, 200)
            with database() as db:
                self.assertIsNone(one(db, "SELECT oid FROM pg_largeobject_metadata WHERE oid=%s", (first_oid,)))
            self.assertEqual(stranger.get(f"/api/videos/{episode_id}").status_code, 403)
            detail = viewer.get(f"/api/series/{show_id}").json()
            self.assertTrue(detail["episodes"][0]["has_video"])
            self.assertFalse(detail["episodes"][0]["can_watch"])
            self.assertFalse(detail["episodes"][0]["video_url"])

            plan = admin.post("/api/admin/plans", json={
                "title": "Тестовый тариф", "price_som": 1000, "duration_days": 30, "active": True,
            })
            self.assertEqual(plan.status_code, 201, plan.text)
            receipt = b"\x89PNG\r\n\x1a\n" + b"test-receipt"
            method = admin.post("/api/admin/payment-methods", json={"title": "Тестовая карта", "details": "0000 0000 0000 0000", "active": True})
            self.assertEqual(method.status_code, 201, method.text)
            self.assertEqual(viewer.get("/api/admin/payment-methods").status_code, 403)
            self.assertEqual(viewer.post("/api/payments", data={"plan_id": plan.json()["id"], "payment_method_id": method.json()["id"]},
                             files={"receipt": ("check.png", receipt, "image/png")}).status_code, 409)
            self.assertEqual(admin.put("/api/admin/settings", json={
                "payment_instructions": "Перевод на тестовую карту: 0000 0000 0000 0000",
                "default_author_percent": 80,
            }).status_code, 200)
            order = viewer.post("/api/payments", data={"plan_id": plan.json()["id"], "payment_method_id": method.json()["id"]},
                                files={"receipt": ("check.png", receipt, "image/png")})
            self.assertEqual(order.status_code, 201, order.text)
            self.assertEqual(admin.get("/api/admin/payment-requests").json()[0]["payment_method_title"], "Тестовая карта")
            order_id = order.json()["id"]
            self.assertEqual(viewer.get(f"/api/admin/payment-requests/{order_id}/receipt").status_code, 403)
            self.assertEqual(admin.get(f"/api/admin/payment-requests/{order_id}/receipt").content, receipt)
            self.assertEqual(admin.put(f"/api/admin/plans/{plan.json()['id']}", json={
                "title": "Тестовый тариф", "price_som": 5000, "duration_days": 60, "active": True,
            }).status_code, 200)
            approval = admin.post(f"/api/admin/payment-requests/{order_id}/review", json={"decision": "approved"})
            self.assertEqual(approval.status_code, 200, approval.text)
            self.assertEqual(admin.post(f"/api/admin/payment-requests/{order_id}/review", json={"decision": "approved"}).status_code, 409)
            subscription = viewer.get("/api/auth/me").json()["subscription"]
            self.assertIsNotNone(subscription)
            self.assertEqual(subscription["ends_at"] - subscription["starts_at"], 30 * 86400)

            partial = viewer.get(f"/api/videos/{episode_id}", headers={"Range": "bytes=5-20"})
            self.assertEqual(partial.status_code, 206, partial.text)
            self.assertEqual(partial.content, video[5:21])
            self.assertEqual(partial.headers["content-range"], f"bytes 5-20/{len(video)}")
            self.assertEqual(viewer.get(f"/api/videos/{episode_id}", headers={"Range": "bytes=999999-"}).status_code, 416)
            self.assertEqual(viewer.get(f"/api/series/{show_id}").json()["episodes"][0]["can_watch"], True)

            session = viewer.post("/api/views/start", json={"episode_id": episode_id}).json()["session_id"]
            with database() as db:
                execute(db, "UPDATE view_sessions SET last_heartbeat=%s,watched_seconds=20 WHERE id=%s", (int(time.time()) - 20, session))
            watched = viewer.post("/api/views/heartbeat", json={"session_id": session})
            self.assertEqual(watched.status_code, 200, watched.text)
            self.assertTrue(watched.json()["counted"])
            with database() as db:
                count = one(db, "SELECT COUNT(*) AS n FROM qualified_views WHERE episode_id=%s", (episode_id,))["n"]
            self.assertEqual(count, 1)
            month = datetime.now(timezone.utc).strftime("%Y-%m")
            second_session = viewer.post("/api/views/start", json={"episode_id": episode_id}).json()["session_id"]
            with database() as db:
                execute(db, "UPDATE view_sessions SET last_heartbeat=%s,watched_seconds=20 WHERE id=%s", (int(time.time()) - 20, second_session))
            self.assertTrue(viewer.post("/api/views/heartbeat", json={"session_id": second_session}).json()["counted"])
            with database() as db:
                self.assertEqual(one(db, "SELECT COUNT(*) AS n FROM qualified_views WHERE episode_id=%s", (episode_id,))["n"], 1)
            report = admin.get(f"/api/admin/finance/{month}").json()
            self.assertEqual(report["actual_revenue_som"], 1000)
            self.assertEqual(report["author_pool_som"], 800)
            self.assertEqual(next(item for item in report["authors"] if item["author_id"] == author_id)["earned_som"], 800)
            self.assertEqual(admin.post("/api/admin/payouts", json={"author_id": author_id, "month": month}).status_code, 409)

            previous_day = datetime.now(timezone.utc).replace(day=1) - timedelta(days=1)
            previous_month = previous_day.strftime("%Y-%m")
            with database() as db:
                execute(db, "UPDATE payment_requests SET reviewed_at=%s WHERE id=%s", (int(previous_day.timestamp()), order_id))
                execute(db, "UPDATE qualified_views SET viewed_on=%s WHERE episode_id=%s", (previous_day.date(), episode_id))
            second_author = admin.post("/api/admin/users", json={
                "full_name": "Второй автор", "email": "author-two@example.com", "password": "author-pass-456", "role": "author",
            })
            self.assertEqual(second_author.status_code, 201, second_author.text)
            second_author_id = second_author.json()["id"]
            second_show = admin.post("/api/admin/series", json={
                "title": "Сериал второго автора", "description": "История", "category_id": category_id,
                "year": 2026, "owner_id": second_author_id,
            })
            self.assertEqual(second_show.status_code, 201, second_show.text)
            second_episode = admin.post(f"/api/admin/series/{second_show.json()['id']}/episodes", json={
                "season": 1, "number": 1, "title": "Пилот второго автора",
            })
            self.assertEqual(second_episode.status_code, 201, second_episode.text)
            self.assertEqual(author.get(f"/api/admin/series/{second_show.json()['id']}").status_code, 403)
            self.assertEqual(author.post(f"/api/admin/episodes/{second_episode.json()['id']}/video", files={"file": ("test.mp4", video, "video/mp4")}).status_code, 403)
            with TestClient(app) as moderator, TestClient(app) as coadmin:
                for client, role in ((moderator, "moderator"), (coadmin, "superadmin")):
                    created = admin.post("/api/admin/users", json={"full_name": "Staff test", "email": f"{role}@example.com", "password": "long-staff-password", "role": role})
                    self.assertEqual(created.status_code, 201, created.text)
                    self.authenticate(client, "/api/admin/login", json={"email": f"{role}@example.com", "password": "long-staff-password"})
                for path in ("/api/admin/users", "/api/admin/payment-requests", f"/api/admin/finance/{month}", "/api/admin/settings"):
                    self.assertEqual(moderator.get(path).status_code, 403, path)
                self.assertEqual(moderator.get("/api/admin/dashboard").status_code, 200)
                self.assertEqual(moderator.get(f"/api/admin/series/{show_id}").status_code, 200)
                self.assertEqual(moderator.put("/api/admin/appearance", json={"theme": "winter"}).status_code, 403)
                self.assertEqual(coadmin.put("/api/admin/appearance", json={"theme": "winter", "hero_title": "Зимняя премьера"}).status_code, 200)
                self.assertEqual(stranger.get("/api/site").json()["theme"], "winter")
                self.assertEqual(coadmin.put("/api/admin/appearance", json={"logo_url": "javascript:alert(1)"}).status_code, 422)
                temporary_video = moderator.post(f"/api/admin/episodes/{second_episode.json()['id']}/video", files={"file": ("test.mp4", video, "video/mp4")})
                self.assertEqual(temporary_video.status_code, 200)
                self.assertEqual(author.delete(f"/api/admin/videos/{temporary_video.json()['id']}").status_code, 403)
                self.assertEqual(moderator.delete(f"/api/admin/videos/{temporary_video.json()['id']}").status_code, 204)
                self.assertEqual(moderator.get(f"/api/admin/series/{second_show.json()['id']}").json()["episodes"][0]["has_video"], False)
                with database() as db:
                    self.assertEqual(one(db, "SELECT COUNT(*) AS n FROM pg_largeobject_metadata")["n"], 1)
                my_id = coadmin.get("/api/auth/me").json()["id"]
                self.assertEqual(coadmin.put(f"/api/admin/users/{my_id}", json={"full_name": "Staff test", "role": "viewer", "is_active": True}).status_code, 409)
            with database() as db:
                for day in (2, 3):
                    viewed_on = previous_day.replace(day=min(day, previous_day.day)).date()
                    execute(db, """INSERT INTO qualified_views (id,user_id,episode_id,author_id,viewed_on,created_at)
                                   VALUES (%s,%s,%s,%s,%s,%s)""",
                            (str(uuid4()), viewer.get("/api/auth/me").json()["id"], episode_id, author_id,
                             viewed_on, int(previous_day.timestamp())))
                execute(db, """INSERT INTO qualified_views (id,user_id,episode_id,author_id,viewed_on,created_at)
                               VALUES (%s,%s,%s,%s,%s,%s)""",
                        (str(uuid4()), viewer.get("/api/auth/me").json()["id"], second_episode.json()["id"],
                         second_author_id, previous_day.date(), int(previous_day.timestamp())))
            override = admin.put(f"/api/admin/finance/{previous_month}", json={"revenue_override_som": 100000, "author_percent": 80})
            self.assertEqual(override.status_code, 200, override.text)
            self.assertEqual(override.json()["author_pool_som"], 80000)
            shares = {row["author_id"]: row["earned_som"] for row in override.json()["authors"]}
            self.assertEqual(shares, {author_id: 60000, second_author_id: 20000})
            self.assertEqual(author.get(f"/api/admin/dashboard?month={previous_month}").json()["earned_som"], 60000)
            payout = admin.post("/api/admin/payouts", json={"author_id": author_id, "month": previous_month})
            self.assertEqual(payout.status_code, 201, payout.text)
            self.assertEqual(payout.json()["amount_som"], 60000)
            self.assertEqual(admin.post("/api/admin/payouts", json={"author_id": author_id, "month": previous_month}).status_code, 409)
            self.assertEqual(admin.put("/api/admin/settings", json={
                "payment_instructions": "Реквизиты для тестовой оплаты", "default_author_percent": 45,
            }).status_code, 200)
            frozen = admin.get(f"/api/admin/finance/{previous_month}").json()
            self.assertEqual(frozen["author_percent"], 80)
            self.assertEqual({row["author_id"]: row["earned_som"] for row in frozen["authors"]}, shares)
            self.assertEqual(admin.put(f"/api/admin/finance/{previous_month}", json={
                "revenue_override_som": 90000, "author_percent": 80,
            }).status_code, 409)
            self.assertEqual(author.delete(f"/api/admin/episodes/{episode_id}").status_code, 204)
            after_delete = admin.get(f"/api/admin/finance/{previous_month}").json()
            self.assertEqual({row["author_id"]: row["earned_som"] for row in after_delete["authors"]}, shares)

            with TestClient(app) as other_admin:
                self.assertEqual(self.authenticate(other_admin, "/api/admin/login", json={
                    "email": "admin-test@kadr.local", "password": "test-password-very-long",
                }).status_code, 200)
                self.assertEqual(admin.post("/api/auth/change-password", json={
                    "current_password": "wrong-password", "new_password": "replacement-password-long",
                }).status_code, 400)
                changed = admin.post("/api/auth/change-password", json={
                    "current_password": "test-password-very-long", "new_password": "replacement-password-long",
                })
                self.assertEqual(changed.status_code, 200, changed.text)
                self.assertEqual(admin.get("/api/admin/session").status_code, 200)
                self.assertEqual(other_admin.get("/api/admin/session").status_code, 401)
                self.assertEqual(self.authenticate(other_admin, "/api/admin/login", json={
                    "email": "admin-test@kadr.local", "password": "test-password-very-long",
                }).status_code, 401)
                self.assertEqual(self.authenticate(other_admin, "/api/admin/login", json={
                    "email": "admin-test@kadr.local", "password": "replacement-password-long",
                }).status_code, 200)
                self.assertEqual(admin.post("/api/admin/logout").status_code, 200)
                self.assertEqual(admin.get("/api/admin/session").status_code, 401)

    def test_email_codes_and_password_reset(self):
        with TestClient(app) as client:
            email = "email-flow@example.com"
            payload = {"full_name": "Email test", "email": email, "password": "initial-password-long"}
            begin = client.post("/api/auth/register", json=payload)
            self.assertEqual(begin.status_code, 201, begin.text)
            challenge = begin.json()["challenge_id"]
            self.assertEqual(client.get("/api/auth/me").status_code, 401)
            with database() as db:
                self.assertIsNone(one(db, "SELECT id FROM users WHERE email=%s", (email,)))
            code = self.codes[email]
            wrong = "000000" if code != "000000" else "111111"
            self.assertEqual(client.post("/api/auth/verify-email", json={"challenge_id": challenge, "code": wrong}).status_code, 400)
            self.assertEqual(client.post("/api/auth/resend-code", json={"challenge_id": challenge}).status_code, 429)
            with database() as db:
                execute(db, "UPDATE auth_challenges SET created_at=created_at-61 WHERE id=%s", (challenge,))
            resent = client.post("/api/auth/resend-code", json={"challenge_id": challenge})
            self.assertEqual(resent.status_code, 200, resent.text)
            self.assertEqual(client.post("/api/auth/verify-email", json={"challenge_id": challenge, "code": code}).status_code, 400)
            challenge = resent.json()["challenge_id"]
            verification = {"challenge_id": challenge, "code": self.codes[email]}
            self.assertEqual(client.post("/api/auth/verify-email", json=verification).status_code, 200)
            self.assertEqual(client.post("/api/auth/verify-email", json=verification).status_code, 400)
            with database() as db:
                execute(db, "UPDATE auth_challenges SET created_at=created_at-61 WHERE email=%s", (email,))
            reset = client.post("/api/auth/reset-password", json={"email": email})
            self.assertEqual(reset.status_code, 200, reset.text)
            reset_id = reset.json()["challenge_id"]
            self.assertEqual(client.post("/api/auth/verify-email", json={"challenge_id": reset_id, "code": self.codes[email], "new_password": "replacement-password-long"}).status_code, 200)
            client.post("/api/auth/logout")
            self.assertEqual(client.post("/api/auth/login", json={"email": email, "password": payload["password"]}).status_code, 401)
            with database() as db:
                execute(db, "UPDATE auth_challenges SET created_at=created_at-61 WHERE email=%s", (email,))
            login = client.post("/api/auth/login", json={"email": email, "password": "replacement-password-long"})
            self.assertEqual(login.status_code, 200)
            self.assertEqual(client.get("/api/auth/me").status_code, 401)
            login_id = login.json()["challenge_id"]
            code = self.codes[email]
            wrong = "000000" if code != "000000" else "111111"
            for _ in range(5):
                self.assertEqual(client.post("/api/auth/verify-email", json={"challenge_id": login_id, "code": wrong}).status_code, 400)
            self.assertEqual(client.post("/api/auth/verify-email", json={"challenge_id": login_id, "code": code}).status_code, 400)
            with database() as db:
                execute(db, "UPDATE auth_challenges SET created_at=created_at-61 WHERE email=%s", (email,))
            expired = client.post("/api/auth/login", json={"email": email, "password": "replacement-password-long"})
            with database() as db:
                execute(db, "UPDATE auth_challenges SET expires_at=0 WHERE id=%s", (expired.json()["challenge_id"],))
            self.assertEqual(client.post("/api/auth/verify-email", json={"challenge_id": expired.json()["challenge_id"], "code": self.codes[email]}).status_code, 400)
            with patch("app.auth.send_code_email", side_effect=HTTPException(status_code=503, detail="SMTP unavailable")):
                failed = client.post("/api/auth/register", json={**payload, "email": "failed-mail@example.com"})
                self.assertEqual(failed.status_code, 503)
            with database() as db:
                self.assertIsNone(one(db, "SELECT id FROM users WHERE email='failed-mail@example.com'"))
                self.assertIsNone(one(db, "SELECT id FROM auth_challenges WHERE email='failed-mail@example.com'"))
            self.assertEqual(client.get("/api/auth/me").status_code, 401)


if __name__ == "__main__":
    unittest.main()
