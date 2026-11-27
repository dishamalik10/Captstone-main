@AGENTS.md

# AURA: working notes for Claude

AURA is a fashion app. It has two parts:
- `Capstone_Agents/`: a FastAPI backend with SQLite and local ML models.
- `Capstone-App/`: an Expo SDK 57 app (iOS, Android, web). Read `Capstone-App/AGENTS.md` before touching it: Expo APIs changed in v57.

The current plan and its decision log are in `ENGINEERING_PLAN.md`; open findings are in `KNOWN_ISSUES.md`. `ARCHITECTURE.md` is a snapshot of commit `d07801c`; where it disagrees with the code, the code wins.

## Verify a change

Run these from the repo root:

- **Backend tests:** `cd Capstone_Agents && .venv/bin/python -m pytest -q`. CI runs the same with `requirements.txt` only. Tests that need OpenCV or MediaPipe skip themselves there, so a test that passes locally can still fail in CI.
- **App type check:** `cd Capstone-App && npx tsc --noEmit`. CI runs this too.
- **Web build:** `cd Capstone-App && npx expo export -p web`. Then check that `dist/_headers` exists and that `dist/index.html` has no inline `<script>`; the CSP would block one.
- **Done means:** tests, `tsc` and the web build are green; the diff is reviewed; anything unverified is named in the report. A test counts as passed only when you ran it.

## Memory is the main constraint

- **Machine profiles ("Option A"):** testers run 8 GB Macs; the public host is a 16 GB Mac. The code defaults are 8 GB-safe: `AURA_TRYON_ENABLED=0` and `AURA_PRELOAD_VISION=0`. The host turns both on in its `.env`. The rollback to "Option B" is written out in the ENGINEERING_PLAN decision log ("Machine profiles"). `tests/test_machine_profile.py` pins the defaults, so changing them is a deliberate, documented decision.
- **Child processes:** heavy, rarely used models run in short-lived child processes (SegFormer in `garment_segmenter.py`, ISNet in `tryon_service.cut_garments`). onnxruntime and TensorFlow keep their memory after use, so a new heavy model follows the same pattern, and you measure the API process before and after adding it (`/health` → `resources`, from localhost).
- **Diffusion model:** the try-on diffusion model lives only in the worker process (`tryon_worker.py`). The API never imports it.
- **Dev server:** run `uvicorn main:app` without `--reload`; reload re-imports every model on each save.

## Backend conventions

- **Settings:** `settings` is a frozen dataclass read once at import. Tests change it with `object.__setattr__(settings, ...)` and restore it in `finally`. Defaults for the test run are in `tests/conftest.py` (rate limits off, try-on on, workers and segmentation off).
- **Schema:** schema changes go in `database.init_database`. Create tables with `CREATE TABLE IF NOT EXISTS`; add a column with an `ALTER TABLE` guarded by `PRAGMA table_info`. Existing user databases upgrade in place, so every change is additive.
- **Routes:** routes in `main.py` stay thin. Logic lives in `services/`, and the API's shapes are in `contracts/api_schemas.py`. Bound every client-supplied string, number and list there (4.8).
- **Uploads:** every uploaded image goes through `image_sanitize.reencode` (it strips EXIF and limits pixel count), and heavy image work runs inside `image_slot()`.
- **Body data:** body photos, measurements and height are body data. Store only what is needed, never log them, never show them to another user, and delete them in `tryon_service.delete_avatars` and on account deletion.
- **Try-on mask:** with no fit information, `body_analysis.tryon_mask` must give the same mask as before. Check a mask change with a real render, not only synthetic tests (see "Widening for ease" in the plan).

## Docs to keep current

When a plan step or a finding changes, update its row in the `KNOWN_ISSUES.md` progress table and the progress notes in `ENGINEERING_PLAN.md`, including deviations and what remains unverified. User-facing setup goes in `README.md`. The tester guide is `TESTING_8GB.md`; owner-only release steps are in `RELEASE.md`.

## Secrets and git

- `.env` files hold secrets. Read their key names, never their values.
- Commit and push only when asked.
- `main` is shared with the team: changes go through a branch and a pull request.
