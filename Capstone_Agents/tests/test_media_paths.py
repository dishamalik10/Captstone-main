"""Stored media references are file names, so data survives moving the upload folder."""
import sqlite3

from database import connection, ensure_user, init_database, utc_now
from services import tryon_service
from services.media_paths import media_name, media_path, migrate_to_names
from settings import settings


def test_names_resolve_inside_the_upload_folder_including_legacy_absolute_paths():
    assert media_name("/old/mac/uploads/abc.jpg") == "abc.jpg"
    assert media_path("abc.jpg") == settings.upload_dir / "abc.jpg"
    assert media_path("/old/mac/uploads/abc.jpg") == settings.upload_dir / "abc.jpg"
    # A stored value can never escape the upload folder.
    assert media_path("../../etc/passwd") == settings.upload_dir / "passwd"


def test_migration_rewrites_legacy_paths_once():
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE t (p TEXT)")
    db.executemany("INSERT INTO t VALUES (?)", [("/a/b/one.jpg",), ("uploads/two.png",), ("three.jpg",), (None,)])
    migrate_to_names(db, "t", ("p",))
    migrate_to_names(db, "t", ("p",))  # idempotent
    assert [r[0] for r in db.execute("SELECT p FROM t ORDER BY rowid")] == ["one.jpg", "two.png", "three.jpg", None]


def test_startup_migrates_wardrobe_and_try_on_paths():
    init_database()
    tryon_service.init_tables()
    ensure_user("media_user")
    with connection() as db:
        db.execute(
            """INSERT INTO clothing_items(item_id,user_id,category,subcategory,garment_group,color_name,
               image_path,confidence,created_at) VALUES(?,?,?,?,?,?,?,?,?)""",
            ("media_item", "media_user", "Top", "Shirt", "g", "White", "/Users/old/uploads/shirt.jpg", "{}", utc_now()),
        )
        db.execute(
            """INSERT INTO avatars(avatar_id,user_id,view,avatar_path,parsing_path,landmarks_json,analysis_json,active,created_at)
               VALUES(?,?,?,?,?,?,?,?,?)""",
            ("media_avatar", "media_user", "front", "/Users/old/uploads/avatar_1.png",
             "/Users/old/uploads/parsing_1.png", "[]", "{}", 1, utc_now()),
        )
    init_database()
    tryon_service.init_tables()
    with connection() as db:
        assert db.execute("SELECT image_path FROM clothing_items WHERE item_id='media_item'").fetchone()[0] == "shirt.jpg"
        assert tuple(db.execute(
            "SELECT avatar_path, parsing_path FROM avatars WHERE avatar_id='media_avatar'").fetchone()) == ("avatar_1.png", "")  # parsing maps are no longer kept (4.3)
    assert tryon_service.owns_media("media_user", settings.upload_dir / "avatar_1.png")
