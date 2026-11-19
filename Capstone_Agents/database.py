from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

from settings import settings


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def connection() -> Iterator[sqlite3.Connection]:
    db = sqlite3.connect(settings.database_path, timeout=30)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    try:
        yield db
        db.commit()
    finally:
        db.close()


def init_database() -> None:
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    with connection() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                display_name TEXT,
                email TEXT UNIQUE,
                password_hash TEXT,
                avatar_url TEXT,
                location TEXT NOT NULL DEFAULT '',
                profile_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS preferences (
                user_id TEXT PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
                preferred_colors TEXT NOT NULL DEFAULT '[]',
                avoided_colors TEXT NOT NULL DEFAULT '[]',
                preferred_styles TEXT NOT NULL DEFAULT '[]',
                disliked_styles TEXT NOT NULL DEFAULT '[]',
                fit_preference TEXT,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS clothing_items (
                item_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                category TEXT NOT NULL,
                subcategory TEXT NOT NULL,
                garment_group TEXT NOT NULL,
                color_name TEXT NOT NULL,
                image_path TEXT NOT NULL,
                confidence TEXT NOT NULL,
                pattern TEXT,
                fabric TEXT,
                fit TEXT,
                texture TEXT,
                seasons TEXT NOT NULL DEFAULT '[]',
                style_tags TEXT NOT NULL DEFAULT '[]',
                occasion_tags TEXT NOT NULL DEFAULT '[]',
                available INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS ix_clothing_user
            ON clothing_items(user_id, available, category);

            CREATE TABLE IF NOT EXISTS recommendations (
                recommendation_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                occasion TEXT NOT NULL,
                item_ids TEXT NOT NULL,
                component_scores TEXT NOT NULL,
                total_score REAL NOT NULL,
                explanation TEXT NOT NULL,
                run_id TEXT,
                rank_position INTEGER,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS feedback (
                feedback_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                recommendation_id TEXT,
                item_ids TEXT NOT NULL,
                action TEXT NOT NULL,
                rating INTEGER,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS products (
                product_id TEXT PRIMARY KEY,
                seller_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                title TEXT NOT NULL,
                price REAL NOT NULL,
                image_urls TEXT NOT NULL DEFAULT '[]',
                category TEXT NOT NULL,
                condition TEXT NOT NULL,
                description TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS orders (
                order_id TEXT PRIMARY KEY,
                buyer_id TEXT NOT NULL REFERENCES users(user_id),
                seller_id TEXT NOT NULL REFERENCES users(user_id),
                product_id TEXT NOT NULL REFERENCES products(product_id),
                amount REAL NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS social_posts (
                post_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                outfit_image_url TEXT NOT NULL,
                caption TEXT NOT NULL,
                product_ids TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS post_likes (
                post_id TEXT NOT NULL REFERENCES social_posts(post_id) ON DELETE CASCADE,
                user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                PRIMARY KEY(post_id, user_id)
            );

            CREATE TABLE IF NOT EXISTS follows (
                follower_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                followed_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                PRIMARY KEY(follower_id, followed_id)
            );

            CREATE TABLE IF NOT EXISTS chat_messages (
                message_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                session_id TEXT NOT NULL DEFAULT 'legacy',
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );
            """
        )
        # Add ranking-slate identifiers to pre-existing databases without dropping
        # user data. Every returned list is now measurable as one recommendation run.
        recommendation_columns = {
            row["name"] for row in db.execute("PRAGMA table_info(recommendations)")
        }
        if "run_id" not in recommendation_columns:
            db.execute("ALTER TABLE recommendations ADD COLUMN run_id TEXT")
        if "rank_position" not in recommendation_columns:
            db.execute("ALTER TABLE recommendations ADD COLUMN rank_position INTEGER")
        db.execute(
            "CREATE INDEX IF NOT EXISTS ix_recommendations_run ON recommendations(run_id, rank_position)"
        )
        db.execute(
            "CREATE INDEX IF NOT EXISTS ix_feedback_recommendation ON feedback(recommendation_id, created_at)"
        )

        # Upgrade databases created by earlier AURA versions.
        existing = {column["name"] for column in db.execute("PRAGMA table_info(users)")}
        for name, definition in {
            "email": "TEXT",
            "password_hash": "TEXT",
            "avatar_url": "TEXT",
            "location": "TEXT NOT NULL DEFAULT ''",
            "profile_json": "TEXT NOT NULL DEFAULT '{}'",
        }.items():
            if name not in existing:
                db.execute(f"ALTER TABLE users ADD COLUMN {name} {definition}")
        clothing_columns = {column["name"] for column in db.execute("PRAGMA table_info(clothing_items)")}
        if "embedding" not in clothing_columns:
            # 512-d float16 visual embedding from the garment CNN (1 KiB per item).
            db.execute("ALTER TABLE clothing_items ADD COLUMN embedding BLOB")
        chat_columns = {column["name"] for column in db.execute("PRAGMA table_info(chat_messages)")}
        if "metadata_json" not in chat_columns:
            db.execute("ALTER TABLE chat_messages ADD COLUMN metadata_json TEXT NOT NULL DEFAULT '{}'")
        if "session_id" not in chat_columns:
            db.execute("ALTER TABLE chat_messages ADD COLUMN session_id TEXT NOT NULL DEFAULT 'legacy'")


def ensure_user(user_id: str, display_name: str | None = None) -> None:
    with connection() as db:
        db.execute(
            """
            INSERT INTO users(user_id, display_name, created_at)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                display_name = COALESCE(excluded.display_name, users.display_name)
            """,
            (user_id, display_name, utc_now()),
        )


def rows(sql: str, parameters: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    with connection() as db:
        return [dict(row) for row in db.execute(sql, parameters).fetchall()]


def row(sql: str, parameters: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    result = rows(sql, parameters)
    return result[0] if result else None


def decode_json_fields(record: dict[str, Any]) -> dict[str, Any]:
    for key in (
        "confidence",
        "seasons",
        "style_tags",
        "occasion_tags",
        "item_ids",
        "component_scores",
        "preferred_colors",
        "avoided_colors",
        "preferred_styles",
        "disliked_styles",
    ):
        if key in record and isinstance(record[key], str):
            record[key] = json.loads(record[key])
    if "available" in record:
        record["available"] = bool(record["available"])
    return record
