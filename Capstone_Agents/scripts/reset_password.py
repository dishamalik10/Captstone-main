"""Reset a user's password by hand (operator tool; AURA does not send reset emails yet).

    python -m scripts.reset_password --email person@example.com

Sets a new random password, ends all of that user's sessions, and prints the new
password once. Send it to the person through the channel they wrote to you from (after
checking it is really them), and tell them to keep it in a password manager.
Nothing is logged.
"""
from __future__ import annotations

import argparse
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database import connection, init_database, row  # noqa: E402
from services.app_service import _password_hash, logout_everywhere  # noqa: E402


def reset(email: str) -> str | None:
    """New password for the account with this email, or None if there is none."""
    record = row("SELECT user_id FROM users WHERE lower(email)=?", (email.strip().lower(),))
    if record is None:
        return None
    password = secrets.token_urlsafe(12)
    with connection() as db:
        db.execute("UPDATE users SET password_hash=? WHERE user_id=?", (_password_hash(password), record["user_id"]))
    logout_everywhere(record["user_id"])
    return password


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--email", required=True)
    args = parser.parse_args()
    init_database()
    password = reset(args.email)
    if password is None:
        print("No account has that email.")
        raise SystemExit(1)
    print(f"New password (shown once): {password}\nAll of this user's sessions were ended.")


if __name__ == "__main__":
    main()
