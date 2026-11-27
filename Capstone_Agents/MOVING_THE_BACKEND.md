# Moving the backend to another machine

The backend's data is two things: the SQLite database and the uploads folder. Stored
photo references are bare file names inside the uploads folder, and relative paths in
`.env` are resolved against `Capstone_Agents/`, so both can be copied as they are.

1. Stop the server on the old machine (so the database is not mid-write).
2. Copy to the new machine, into `Capstone_Agents/`:
   - `aura.db` (or whatever `AURA_DATABASE_PATH` points to)
   - `uploads/` (or `AURA_UPLOAD_DIR`)
   - `.env`: keep **the same `AURA_MEDIA_SIGNING_KEY`**, otherwise image links already
     held by the app stop working until users refresh.
   - Model files under `model_artifacts/` that are not in Git (GGUFs, `tryon/`), or
     download them again with the `training/download_*.py` scripts.
3. On a machine without enough memory for try-on (for example a free cloud VM), set
   `AURA_TRYON_ENABLED=0` in `.env`.
4. Install and start:
   ```bash
   python3.11 -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt            # plus requirements-local.txt for local LLMs / try-on
   python -m uvicorn main:app --host 127.0.0.1 --port 8000
   ```
5. Point the tunnel (or reverse proxy) for `api.yourdomain.com` at the new machine.
   The app's `EXPO_PUBLIC_API_URL` does not change, so no new APK is needed.

On first start, any database rows that still hold old absolute paths are rewritten to
file names automatically.
