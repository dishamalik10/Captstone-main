import os
import tempfile


# Configure isolation before pytest imports any service module during collection.
os.environ["AURA_DATABASE_PATH"] = tempfile.mkdtemp(prefix="aura-test-") + "/test.db"
os.environ["AURA_UPLOAD_DIR"] = tempfile.mkdtemp(prefix="aura-uploads-")
