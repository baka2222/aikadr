"""One-time cleanup of identified prototype rows; never runs on startup."""

from .db import database, execute, one


DEMO_SERIES = {
    "4c2658e7-3fc2-4ca3-ada1-20c37dcee84e": "Ночной маршрут",
    "389c45c9-9873-49a9-93c6-05e76d9898f2": "Тихая вода",
    "bedaed22-87e1-4092-a88e-84b35fdcac1f": "Город 2099",
}


def main():
    removed = []
    with database() as db:
        for row_id, title in DEMO_SERIES.items():
            row = one(db, "SELECT * FROM series WHERE id=%s FOR UPDATE", (row_id,))
            if not row or row["title"] != title or row["owner_id"]:
                continue
            used = one(db, """SELECT 1 FROM episodes e WHERE e.series_id=%s AND (
                          EXISTS (SELECT 1 FROM videos v WHERE v.episode_id=e.id)
                          OR EXISTS (SELECT 1 FROM qualified_views q WHERE q.episode_id=e.id)
                          OR (e.video_url<>'' AND e.video_url NOT LIKE 'https://interactive-examples.mdn.mozilla.net/%%')) LIMIT 1""", (row_id,))
            if used:
                continue
            execute(db, "DELETE FROM series WHERE id=%s", (row_id,))
            removed.append(title)
        plans = execute(db, """DELETE FROM plans p WHERE id='d3df3a8f-9961-45e5-b72b-c8b7f88ec079'
                         AND title='Месяц' AND price_som=1990 AND duration_days=30
                         AND description='Доступ ко всем сериалам на 30 дней'
                         AND NOT EXISTS (SELECT 1 FROM payment_requests r WHERE r.plan_id=p.id)
                         AND NOT EXISTS (SELECT 1 FROM subscriptions s WHERE s.plan_id=p.id)""")
    print(f"Removed prototype series: {len(removed)}; prototype plans: {plans}. Other content preserved.")


if __name__ == "__main__":
    main()
