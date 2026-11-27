import os
import tempfile


# Configure isolation before pytest imports any service module during collection.
os.environ["AURA_DATABASE_PATH"] = tempfile.mkdtemp(prefix="aura-test-") + "/test.db"
os.environ["AURA_UPLOAD_DIR"] = tempfile.mkdtemp(prefix="aura-uploads-")
os.environ.setdefault("AURA_MEDIA_SIGNING_KEY", "test-only-signing-key")
os.environ.setdefault("AURA_PRELOAD_VISION", "0")  # tests stub the CNN; avoid a 6 s load per run
os.environ.setdefault("AURA_RATE_LIMITS", "0")  # the suite signs up hundreds of users; tests/test_rate_limits.py turns it on
os.environ.setdefault("AURA_TRYON_ISOLATE_CUTOUT", "0")  # tests patch the cutter in-process
os.environ.setdefault("AURA_TRYON_SPAWN_WORKER", "0")
os.environ.setdefault("AURA_TRYON_ENABLED", "1")  # the try-on tests need it; the app default is off (8 GB-safe)
os.environ.setdefault("AURA_GARMENT_SEGMENTATION", "0")  # same results with or without the model; tests opt in  # tests drive renders with process_next()
# Pin ranking weights to their documented defaults so a developer's .env (load_dotenv
# never overrides variables that are already set) cannot change test results.
os.environ["AURA_OUTFIT_COMPAT_WEIGHT"] = "0.15"
os.environ["AURA_LOG_DIR"] = tempfile.mkdtemp(prefix="aura-logs-")


import pytest  # noqa: E402  (after the environment set-up above, on purpose)


@pytest.fixture
def remove_new_listings():
    """Delete listings (and their orders) a test created: other tests assert exact browse results."""
    from database import connection, init_database

    init_database()
    with connection() as db:
        before = {r[0] for r in db.execute("SELECT product_id FROM products")}
    yield
    with connection() as db:
        created = [r[0] for r in db.execute("SELECT product_id FROM products") if r[0] not in before]
        for product_id in created:
            db.execute("DELETE FROM orders WHERE product_id=?", (product_id,))
            db.execute("DELETE FROM products WHERE product_id=?", (product_id,))
