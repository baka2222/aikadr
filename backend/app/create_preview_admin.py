"""Create one locally managed superadmin account for inspecting the studio."""

import secrets
import time
from uuid import uuid4

from .db import database, execute, one
from .security import hash_password


EMAIL = "owner-preview@aikadr.local"


def main():
    password = secrets.token_urlsafe(26)
    with database() as db:
        if one(db, "SELECT id FROM users WHERE email=%s", (EMAIL,)):
            raise SystemExit("Preview admin already exists; no password was changed")
        execute(db, """INSERT INTO users (id,email,full_name,password_hash,role,is_active,email_verified,created_at)
                   VALUES (%s,%s,%s,%s,'superadmin',TRUE,TRUE,%s)""",
                (str(uuid4()), EMAIL, "Владелец проекта", hash_password(password), int(time.time())))
    print(f"Email: {EMAIL}\nPassword: {password}\nLogin: /admin")


if __name__ == "__main__":
    main()
