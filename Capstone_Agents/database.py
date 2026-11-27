from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Iterator

from services.media_paths import migrate_to_names
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

            -- Report and block (4.4, services/moderation_service.py). Reports are reviewed
            -- by hand with scripts/review_reports.py; the snapshot keeps the evidence.
            CREATE TABLE IF NOT EXISTS reports (
                report_id TEXT PRIMARY KEY,
                reporter_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                target_type TEXT NOT NULL,
                target_id TEXT NOT NULL,
                target_owner_id TEXT,
                reason TEXT NOT NULL,
                details TEXT NOT NULL DEFAULT '',
                snapshot_json TEXT NOT NULL DEFAULT '{}',
                status TEXT NOT NULL DEFAULT 'open',
                created_at TEXT NOT NULL,
                resolved_at TEXT,
                UNIQUE(reporter_id, target_type, target_id)
            );
            CREATE INDEX IF NOT EXISTS ix_reports_status ON reports(status, created_at);

            CREATE TABLE IF NOT EXISTS blocks (
                blocker_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                blocked_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                created_at TEXT NOT NULL,
                PRIMARY KEY (blocker_id, blocked_id)
            );
            CREATE INDEX IF NOT EXISTS ix_blocks_blocked ON blocks(blocked_id);

            -- Import previews (4.2b, services/import_previews.py): the photo and candidate
            -- cut-outs shown before an item is created. Deleted after 1 hour.
            CREATE TABLE IF NOT EXISTS import_previews (
                preview_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                source_url TEXT,
                source_title TEXT,
                suggested_category TEXT,
                person_found INTEGER NOT NULL DEFAULT 0,
                files_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS ix_import_previews_expiry ON import_previews(expires_at);

            -- Body measurements in cm (4.11, services/body_measurements.py). Body data:
            -- deleted with "Delete my body data" and with the account.
            CREATE TABLE IF NOT EXISTS body_measurements (
                user_id TEXT PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
                estimate_json TEXT NOT NULL DEFAULT '{}',
                manual_json TEXT NOT NULL DEFAULT '{}',
                meta_json TEXT NOT NULL DEFAULT '{}',
                updated_at TEXT NOT NULL
            );

            -- Rate-limit events (services/rate_limits.py); old rows are pruned on use.
            CREATE TABLE IF NOT EXISTS rate_events (
                bucket TEXT NOT NULL,
                key TEXT NOT NULL,
                at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS ix_rate_events ON rate_events(bucket, key, at);

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

            CREATE TABLE IF NOT EXISTS bandit_models (
                user_id TEXT PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
                state_json TEXT NOT NULL,
                updates INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL
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

            -- Marketplace buyer <-> seller chat: one conversation per (listing, buyer).
            CREATE TABLE IF NOT EXISTS conversations (
                conversation_id TEXT PRIMARY KEY,
                product_id TEXT NOT NULL REFERENCES products(product_id) ON DELETE CASCADE,
                buyer_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                seller_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(product_id, buyer_id)
            );

            CREATE TABLE IF NOT EXISTS conversation_messages (
                message_id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL REFERENCES conversations(conversation_id) ON DELETE CASCADE,
                sender_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                body TEXT NOT NULL,
                created_at TEXT NOT NULL,
                read_at TEXT
            );

            CREATE INDEX IF NOT EXISTS ix_conversation_messages
            ON conversation_messages(conversation_id, created_at);
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
            # When the user confirmed "this is me, I'm 18+, store my photo" (4.3).
            "body_consent_at": "TEXT",
        }.items():
            if name not in existing:
                db.execute(f"ALTER TABLE users ADD COLUMN {name} {definition}")
        # Profile pictures must be photos AURA stored (4.8). Older rows held device-local
        # paths (file://, blob:) or outside URLs, which other users' apps would fetch.
        db.execute(
            "UPDATE users SET avatar_url=NULL WHERE avatar_url IS NOT NULL AND avatar_url NOT LIKE '/marketplace/images/%'"
        )
        clothing_columns = {column["name"] for column in db.execute("PRAGMA table_info(clothing_items)")}
        if "embedding" not in clothing_columns:
            # 512-d float16 visual embedding from the garment CNN (1 KiB per item).
            db.execute("ALTER TABLE clothing_items ADD COLUMN embedding BLOB")
        for name in ("source_url", "source_title"):
            # Shop link and product title for items imported from a shopping link.
            if name not in clothing_columns:
                db.execute(f"ALTER TABLE clothing_items ADD COLUMN {name} TEXT")
        if "category_source" not in clothing_columns:
            # "user" when the user confirmed a category the CNN disagreed with (4.2b): it
            # is kept as chosen and the item is flagged for review.
            db.execute("ALTER TABLE clothing_items ADD COLUMN category_source TEXT")
        if "size_json" not in clothing_columns:
            # Garment size (4.11): {"label", "chart", "measurements": {...flat cm}}; NULL = unknown.
            db.execute("ALTER TABLE clothing_items ADD COLUMN size_json TEXT")
        if "donated_at" not in clothing_columns:
            # Set when the user donates an unworn item; the item is also marked unavailable.
            db.execute("ALTER TABLE clothing_items ADD COLUMN donated_at TEXT")
        preview_columns = {column["name"] for column in db.execute("PRAGMA table_info(import_previews)")}
        if "suggested_size" not in preview_columns:
            # A size read from the shop page (4.11), offered at confirm time.
            db.execute("ALTER TABLE import_previews ADD COLUMN suggested_size TEXT")
        # Photos are stored by file name inside the upload folder (portable data).
        migrate_to_names(db, "clothing_items", ("image_path",))
        # Marketplace listing details and order delivery info.
        product_columns = {column["name"] for column in db.execute("PRAGMA table_info(products)")}
        for name in ("size", "brand", "wardrobe_item_id", "updated_at"):
            if name not in product_columns:
                db.execute(f"ALTER TABLE products ADD COLUMN {name} TEXT")
        # Where a slate was shown (M6): "recommend" (outfit screen) or "chat". Rows written
        # before this column existed cannot be told apart and default to "recommend".
        if "surface" not in recommendation_columns:
            db.execute("ALTER TABLE recommendations ADD COLUMN surface TEXT NOT NULL DEFAULT 'recommend'")
        if "explanation_source" not in recommendation_columns:
            db.execute("ALTER TABLE recommendations ADD COLUMN explanation_source TEXT")
        order_columns = {column["name"] for column in db.execute("PRAGMA table_info(orders)")}
        for name in ("shipping_address", "payment_method", "updated_at", "reserved_until"):
            if name not in order_columns:
                db.execute(f"ALTER TABLE orders ADD COLUMN {name} TEXT")
        # Orders placed before reservations existed get the same 72 h hold from their creation.
        for order in db.execute(
            "SELECT order_id, created_at FROM orders WHERE status='pending' AND reserved_until IS NULL"
        ).fetchall():
            created = datetime.fromisoformat(order["created_at"])
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            db.execute("UPDATE orders SET reserved_until=? WHERE order_id=?",
                       ((created + timedelta(hours=72)).isoformat(), order["order_id"]))
        db.execute("CREATE INDEX IF NOT EXISTS ix_orders_pending ON orders(status, reserved_until)")
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
