"""Assign a role to an existing account from the backend directory."""

import argparse
from contextlib import closing

from app.database import db
from app.schemas.auth import Credentials, role_for_email


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("email")
    parser.add_argument("role", choices=db.USER_ROLES)
    args = parser.parse_args()
    email = Credentials.normalize_email(args.email)
    expected_role = role_for_email(email)
    if args.role != expected_role:
        parser.error(f"This email domain can only be assigned the {expected_role} role.")

    with closing(db.connect()) as connection:
        db.init_db(connection)
        with connection:
            updated = connection.execute(
                "UPDATE users SET account_role = ? WHERE email = ? RETURNING id",
                (args.role, email),
            ).fetchone()
            if updated is None:
                parser.error("Account does not exist. Sign up first.")
            connection.execute("DELETE FROM user_sessions WHERE user_id = ?", (updated["id"],))

    print(f"Role for {email} is now {args.role}.")


if __name__ == "__main__":
    main()
