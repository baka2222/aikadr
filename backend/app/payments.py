"""Payment review shared by the web admin and Telegram bot."""

import time
from uuid import uuid4

from fastapi import HTTPException

from .db import database, execute, one


def review_payment(request_id: str, decision: str, reviewer_id: str, note: str = ""):
    if decision not in ("approved", "rejected"):
        raise HTTPException(status_code=422, detail="Неверное решение")
    with database() as db:
        row = one(db, "SELECT * FROM payment_requests WHERE id=%s FOR UPDATE", (request_id,))
        if not row:
            raise HTTPException(status_code=404, detail="Заявка не найдена")
        if row["status"] != "pending":
            raise HTTPException(status_code=409, detail="Заявка уже обработана")
        now = int(time.time())
        execute(db, """UPDATE payment_requests SET status=%s,reviewer_id=%s,reviewed_at=%s,note=%s WHERE id=%s""",
                (decision, reviewer_id, now, note[:1000], request_id))
        if decision == "approved":
            previous = one(db, "SELECT MAX(ends_at) AS ends_at FROM subscriptions WHERE user_id=%s", (row["user_id"],))
            start = max(now, previous["ends_at"] or now)
            execute(db, """INSERT INTO subscriptions (id,user_id,plan_id,payment_request_id,starts_at,ends_at)
                           VALUES (%s,%s,%s,%s,%s,%s)""",
                    (str(uuid4()), row["user_id"], row["plan_id"], request_id, start, start + row["duration_days"] * 86400))
        return {"id": request_id, "status": decision}
