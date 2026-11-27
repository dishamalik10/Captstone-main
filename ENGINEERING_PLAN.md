# ENGINEERING_PLAN

Audit revision 2 (commit `d07801c`), updated with the decisions from the 2026-11-27 Q&A session. Issue IDs refer to `KNOWN_ISSUES.md`, and decision IDs (Q1–Q22) refer to the decision log below.

## 1. Target release (decided)

| Area | Decision | Q |
|---|---|---|
| Audience | Open sign-up for anyone, sized for 50–100 users with a few active at once | Q1, Q1b, Q1c |
| Product stance | An ongoing product, with demo-breaking items fixed first | Q2 |
| Backend host | **The project owner's 16 GB Apple Silicon Mac** (corrected 2026-11-27; earlier recorded as 8 GB) | Q1a, Q3 |
| Development and testing | **8 GB Macs must run the app.** Code defaults and `.env.example` are 8 GB-safe: try-on off, CNN loaded on first use. The host turns both on in its `.env` (decision log: "Machine profiles") | — |
| Portability | Keep the backend movable to an Oracle Cloud Always-Free ARM VM (or a 16 GB CPU VM), with try-on turned off there. No move planned yet | Q14 |
| Public URL | A Cloudflare **named** tunnel on an owned domain: `api.yourdomain.com` (HTTPS). Uvicorn listens on `127.0.0.1` only | Q7 |
| Uptime | The app is down whenever the Mac sleeps or the server isn't running. There is no launchd service and no keep-awake. Clients must handle this gracefully | Q13 |
| Start command | `python -m uvicorn main:app --host 127.0.0.1 --port 8000` (**no `--reload`**) plus `cloudflared tunnel run aura`. The API starts the try-on worker itself | Q13, Q15 |
| Android | APK built with **EAS Build** (APK profile), package ID **`com.aurastylist.app`**, EAS-managed signing key, published on **GitHub Releases** | Q17 |
| iPhone | The **web app** (Safari, "Add to Home Screen"). No Apple Developer Program for now | Q20 |
| Web | The `npx expo export -p web` output hosted on **Cloudflare Pages** at `app.yourdomain.com`. Android users can also use it | Q20, Q21 |

```
Android APK ──┐
              ├──▶ https://api.yourdomain.com ──(Cloudflare tunnel)──▶ Mac: uvicorn 127.0.0.1:8000
Web (Pages) ──┘        (CORS: only app.yourdomain.com)                 ├─ SQLite + uploads/
app.yourdomain.com                                                     ├─ stylist 1.5B GGUF (chat + picking)
                                                                       └─ child process: try-on worker
```

## 2. Ground rules

1. Tests first. Each fix lands with a test that fails before the change.
2. Small PRs, one issue or a tightly related group each.
3. Don't retune ranking weights, bandit priors or occasion tables without the ranking snapshot test (step 1.3).
4. Run only **one** uvicorn process. Realtime and try-on coordination depend on it.
5. Nothing is published (APK or web) until step 4 is complete.
6. Before every merge, run `python -m pytest -q` (all green after step 1.1) and `tsc --noEmit`.

---

## Step 1: Foundations

| # | Work | Addresses | Q |
|---|---|---|---|
| 1.1 | Make the suite pass without the optional extras: `pytest.importorskip("cv2")` and `importorskip("mediapipe")` in `tests/test_virtual_tryon.py`. Declare `opencv-python` in `requirements-local.txt`. Add CI running pytest (core) and `tsc --noEmit` | M11, L9 | — |
| 1.2 | Logging: INFO and above to a rotating `Capstone_Agents/logs/aura.log` (5 × 10 MB, git-ignored); **only WARNING and above to the terminal**; a request ID on every line; **never log user content** (chat text, photos, addresses, tokens). Add a global exception handler that returns a generic 500 body. Scrub paths and raw exception text from `/health`, `last_error` and try-on `error` | M10 | Q18 |
| 1.3 | Ranking snapshot test: a fixed wardrobe, fixed feedback and a seeded bandit RNG, asserting the order of results | M11, M18 | — |
| 1.4 | Characterisation tests for the remaining gaps: wrong password; expired session; duplicate signup; like a missing post; follow a missing user; concurrent orders; a DNS-rebinding stub; try-on flooding; an old-schema migration | M11, M3 | — |
| 1.5 | Portable paths: resolve relative `.env` paths against `ROOT`. Store **basenames** for wardrobe, avatar, parsing and render files, with a migration. Match ownership by file name. Write a short "move to a VM" guide (copy `aura.db` + `uploads/`, set `AURA_TRYON_ENABLED=0`) | M14 | Q14 |
| 1.6 | Stable signing key: refuse to start without `AURA_MEDIA_SIGNING_KEY` outside tests, and set it in the local `.env`. Remove `--reload` from the docs | M5 | Q13 |

## Step 2: Stop freezes and limit the work

| # | Work | Addresses | Q |
|---|---|---|---|
| 2.1 | Make `upload_clothing`, `purchase_impact` and `upload_avatar` plain `def` routes (read uploads via `file.file`). Pre-load the CNN in `lifespan`. Cap concurrent image and body processing at **2** with a semaphore. Measured on the dev Mac: CNN warm inference takes 0.063 s, the first load 6.04 s, and 4 concurrent calls 0.13 s | H3 | Q4 |
| 2.2 | Chat from the stylist: set the default `AURA_CHAT_USE_STYLIST=1`, so only the ~1 GB stylist GGUF is resident. Qwen 3B is no longer the default. Update the README | H4 | Q8 |
| 2.3 | Try-on worker process: the API spawns it as a **child process** at startup and stops it on shutdown. It reads jobs from the `tryon_renders` table, replacing the in-memory queue. Limits: **1 active render per user**, **3 renders per user per day**, a **global queue of 10** (429 "busy, try later" above that). Add `DELETE /tryon/{id}`. Delete unsaved renders after **7 days**. `AURA_TRYON_ENABLED=0` turns it off | H4, H5, L22 | Q9, Q15 |
| 2.4 | Marketplace holds: conditional `UPDATE ... WHERE status='active'` with a `rowcount` check. A `reserved_until` column, so `pending` orders auto-cancel after **72 h** and relist the item. At most **3 open orders per buyer**. Show "payment arranged with the seller (COD/UPI)" in checkout | M15 | Q16 |
| 2.5 | Bandit: fetch candidate embeddings once and reuse them. `learn_from_feedback` queries only the outfit's items. Its read-update-write runs in one `BEGIN IMMEDIATE` transaction. Read the prior's compatibility weight from `settings` | M18 | Q6 |
| 2.6 | Slate integrity: one transaction per slate. Persist the final explanation and its source. Add a `surface` column (or stop persisting chat candidates), and exclude chat in `evaluate_feedback.py` | M7, M6 | — |
| 2.7 | Map `IntegrityError` to 409/404 in the global handler, and check that targets exist in like, follow and conversation start | M3 | — |

## Step 3: Measure memory (go/no-go for public try-on)

| # | Work | Addresses | Q |
|---|---|---|---|
| 3.1 | On the dev Mac, run the stylist GGUF, TensorFlow models, MediaPipe and the try-on worker mid-render, while chat and recommend requests are in flight. Record peak RSS for both processes and the swap in use | H4 | Q9, Q19 |
| 3.2 | **Rule** (written for an 8 GB host; now the guide for an 8 GB tester who turns try-on on): if combined peak memory stays **under about 6.5 GB without heavy swap**, try-on stays on for the public release. Otherwise, set `AURA_TRYON_ENABLED=0` for the public release and keep try-on for demos only | H4 | Q9 |
| 3.3 | Report resident models and RSS in `/health` (authenticated or minimal, see 4.8) | H4 | — |

**Result (2026-11-27, dev Mac, 16 GB): GO, with about 0.5 GB of headroom against the 8 GB budget.** The host is now this 16 GB Mac, so the host has ~10 GB of headroom. The 8 GB budget still matters for teammates who turn try-on on (not yet measured on an 8 GB Mac). Measured with macOS `footprint` (memory that counts toward pressure, including compressed/swapped and Metal) once a second during a real 2-layer render (synthetic avatar, 384×512, 30 steps), with chat and recommend requests sent alongside it the whole time:

| | Before fix | After fix |
|---|---|---|
| Try-on worker peak | 7.8 GB | **5.1 GB** |
| API peak (stylist GGUF + CNN + compat + MediaPipe) | 0.7 GB | 0.9 GB |
| Combined peak | 8.5 GB (no-go) | **6.0 GB** (go) |
| Swap growth during the run | +4.1 GB | +0.3 GB |
| Render time | 4 min 19 s | 4 min 33 s |

- **Cause of the 7.8 GB:** the ISNet garment cut-out runs at 1024×1024 on CPU and onnxruntime keeps ~2–2.7 GB after use (turning off its memory arena didn't help). **Fix:** `cut_garments` cuts every garment in a short-lived child process before the diffusion model runs (`AURA_TRYON_ISOLATE_CUTOUT=1`), and CatVTON calls `torch.mps.empty_cache()` after each layer, so an idle loaded model holds ~2.8 GB, not ~5 GB. The output was unchanged: 4 of 786k pixels differ, by ≤12 levels (Metal nondeterminism).
- **Not measured:** a second render while the model is still loaded runs the cut-out child (~2.2 GB) beside the idle model (~2.8 GB): an estimated 0.9 + 2.8 + 2.2 ≈ 5.9 GB. Also not measured on an actual 8 GB Mac, where macOS and other apps take their share; re-check `/health` → `resources` there before release.
- **Latency while rendering:** recommend median 0.10 s; chat median ~10 s, worst 46 s, because the GPU is shared with the render.

## Step 4: Harden, then ship

| # | Work | Addresses | Q |
|---|---|---|---|
| 4.1 | Rate limits, keyed on account and **`CF-Connecting-IP`**: 5 failed logins per account per 15 min; 5 sign-ups per IP per day; 20 chat messages per user per hour; 30 recommendations per user per hour; 50 uploads per user per day; at most 3 WebSockets per user; unauthenticated sockets closed after 10 s; typing events throttled. No email verification in v1 | H2, L18 | Q12 |
| 4.2 | SSRF fix: connect only to the IP that passed the check (pinned adapter with the right SNI and Host header), a **20 s** limit on the whole fetch, **10 imports per user per hour**. **If this isn't done, link import is turned off before release** | M17 | Q11 |
| 4.2b | **Garment isolation for imports and uploads** (see §4.2b below). Today the MediaPipe segmenter has a single "clothes" class, so a model photo yields the whole outfit. The fix: choose a product photo with no model in it, user-confirmed target category, SegFormer-B2 Clothes garment segmentation, and a preview/confirm step. **Not a release blocker:** if SegFormer slips, ship the model-free photo choice and the preview screen | link-import quality | LQ1–LQ11 |
| 4.3 | Privacy: a consent screen before the first avatar upload ("this is me, I'm 18+, I agree to storage"); a visible **Delete my body data** button (backed by `DELETE /avatar`); delete parsing maps and landmarks after the avatar is built; **Delete my account**, cascading through every table and file (orders anonymised); a privacy policy page linked from GitHub Releases and the web app | H6, M12, L15 | Q10 |
| 4.4 | Report and block: users can report a listing, a marketplace message or a social post, and block a user. Blocked users can't message you, and their content is hidden. Reports go into a `reports` table that you review by hand | open sign-up gap | final confirmation |
| 4.5 | Chat grounding: check each reply for garment terms that aren't in the shown outfit or the wardrobe. Regenerate once, then fall back to the deterministic reply. Track the rate of invented pieces on a fixed prompt set for the report | M16 | Q5 |
| 4.6 | Frontend session handling: clear the token **only on 401**; add an axios 401 interceptor; show a "can't reach AURA's server" screen on network errors; close the realtime socket on logout; don't log out on a profile-setup failure | M9 | Q13 |
| 4.7 | Web-specific: CORS allows only `app.yourdomain.com`; a strict Content-Security-Policy via Cloudflare Pages `_headers`; **7-day sessions for web clients**; a "log out of all devices" option. Tokens stay in `localStorage` for v1 | L3 | Q21, Q22 |
| 4.8 | Remaining input and response hygiene: `EmailStr`; `max_length` on the remaining fields; media-ID-only `avatarUrl`, `outfit_image_url` and `ProductCreate.image_urls` (or remove the JSON create route); decode and re-encode every upload, including public listing photos, and strip EXIF; authenticated `/weather` with per-city caching; minimal unauthenticated `/health` and `/tryon/status`; a generic signup-conflict message | M4, M2, L4, L5, L19 | — |
| 4.9 | Release Android: add `android.package: "com.aurastylist.app"` to `app.json` and an `eas.json` with an APK profile, with `EXPO_PUBLIC_API_URL=https://api.yourdomain.com`. Run `eas build -p android --profile preview` and publish on GitHub Releases with install notes ("allow unknown apps") | — | Q17 |
| 4.10 | Release web: `npx expo export -p web` with the same API URL, deployed to Cloudflare Pages at `app.yourdomain.com`, with iPhone "Add to Home Screen" instructions | — | Q20, Q21 |
| 4.11 | **Virtual Look fit** (see §4.11 below; do it before 4.9/4.10): measurements in cm from front and side photos scaled by height, garment size labels with a generic size chart, size advice per body zone, and a try-on mask built from the body outline. **Release check:** a tape-measured accuracy test on 5–10 volunteers before deploying | Virtual Look quality | VQ1–VQ15 |

**Progress (2026-11-27, uncommitted): 4.1–4.8 and 4.2b are implemented** (see the KNOWN_ISSUES.md progress table for evidence). Backend: 268 tests pass locally, and 266 pass with 2 model-dependent skips in a clean environment with the CI requirements. App: `tsc --noEmit` is clean and the web export builds. Deviations from the designs above:
- **4.2b, where SegFormer runs:** the ONNX export (same weights) runs on onnxruntime, not torch. Each call runs in a short-lived child process, one at a time, not lazily loaded in the API with a 10-minute unload. Reason: measured in the API process, one run left ~0.9–1.2 GB resident that was never returned, more than the step-3 headroom. In a child, the API gains nothing and the child peaks at ~0.43 GB for ~0.7–1.3 s.
- **4.2b, scope:** "Remove model from photo" keeps its direct route and uses the item's saved category instead of opening a preview. `POST /wardrobe/upload` and `/wardrobe/import-link` still work for older clients (the cut-out follows the CNN's category). The app uses the preview routes.
- **4.5:** the check is colour-aware ("light blue t-shirt" is invented if only a white one is owned). Sentences phrased as an idea ("if you have…") or a gap ("you don't have a blazer") may name other pieces.
- **4.8:** email is checked with a pattern instead of `EmailStr`, so no new `email-validator` dependency. Full `/health` details are given only on the server machine itself, not to signed-in users.

Not yet verified: any of the new screens on a real phone or browser; render-time re-parsing on a real person photo; the CSP with the real domain; the CI workflow on GitHub. In 3 of ~7 local runs the test process took up to 16 minutes to *exit* after all tests had passed (in 40–70 s). This was seen while the `uvicorn --reload` dev server was running and 2.7 GB of swap was in use; the cause is not confirmed.

**Progress (2026-11-27, uncommitted): 4.11 is implemented; 4.9 and 4.10 are prepared** (code and config; the builds and deploys need the owner's accounts, see `RELEASE.md`).

- **4.11 code:**
  - `services/body_measurements.py`: outline geometry, ellipse circumferences, typed-over-estimate merge, ranges until validated.
  - `services/size_chart.py`, `services/fit_advice.py` and `services/tryon_fit.py`.
  - `MaskFit` in `body_analysis.tryon_mask`.
  - Routes: `GET`/`PUT /body/measurements`, `POST /body/measurements/estimate`, `GET /wardrobe/{user}/{item}/fit` and `GET /marketplace/products/{id}/fit`.
  - Migrations: the `body_measurements` table, `clothing_items.size_json` and `import_previews.suggested_size`.
  - The volunteer check: `scripts/measurement_accuracy.py` and `training/MEASUREMENT_ACCURACY_PROTOCOL.md`.
  - App: the Body measurements card, size editor and fit advice cards, and a size field in the import preview.
- **Tests:** `tests/test_fit_sizing.py` (28) covers synthetic silhouettes with known widths and depths, the ellipse maths, typed values winning, ranges until validated, size chart labels, rating boundaries, advice from the chart, measurements and usual sizes, the mask's hem and width, routes, deletion with body data, and the side photo not being stored. Without size information the try-on mask was checked to be byte-identical to the previous version on all three regions.
- **4.9 and 4.10:**
  - `app.json` has `android.package: com.aurastylist.app`.
  - `eas.json` has `preview` and `production` APK profiles with `EXPO_PUBLIC_API_URL` (placeholder domain) and `appVersionSource: remote`, per the Expo docs.
  - `RELEASE.md` has the owner's steps, the install notes and the iPhone "Add to Home Screen" instructions.
- **For 8 GB testers:** `TESTING_8GB.md` and `scripts/machine_check.py`.
- **Found before release: "Forgot password" said a reset link was sent, but nothing was ever sent** (there is no email backend). The screen now says AURA can't send reset emails yet and links to support. The operator resets the password with `scripts/reset_password.py`, which sets a one-time random password and ends all of that user's sessions; it is tested in `tests/test_privacy.py`. Real email reset and an in-app "change password" are not built; that is an owner decision (it needs an email provider).

Deviations from §4.11:
- **Weight is not collected.** The method doesn't use it (data minimisation).
- **The capture guide is a tip list, not a silhouette overlay on a live camera.** The app uses the system camera through the image picker; an overlay needs a custom camera screen.
- **The measuring side photo is a separate upload that is never written to disk.** The existing optional side *avatar* for side-on try-on is unchanged.
- **Height is removed by "Delete my body data"**, together with measurements.
- **The try-on mask keeps following the body and the clothes in the photo.** With size information, its hem moves; without it, nothing changes. Replacing the clothes-following part was not done, because its effect on renders could not be checked.
- **Widening for ease is built but off** (`AURA_TRYON_FIT_WIDEN=0`). One render check (CC0 test photo, 2026-11-27, about 2 min per render on the 16 GB Mac) compared three masks:
  - default mask: unchanged;
  - crop hem: changed the mask only slightly on that photo, with no visible harm;
  - widened mask: rendered as a flat bar at the hips, not looser fabric.
- **Some numbers are heuristic constants, not validated:**
  - the ease targets, the cut and preference shifts, and the rating boundaries;
  - the ±5% (lengths ±4%) range shown around an estimate.
- **The generic chart has women's, men's and "unisex" (the average) letter sizes.**
- **How a bare number is read:**
  - on a bottom: waist in inches;
  - on a top: chest in inches;
  - otherwise: a UK women's size.
- **Listing advice also uses the seller's garment measurements** when the listing was made from a wardrobe item (garment data, not body data).

Not yet verified for 4.11:
- the estimates against a tape measure (the volunteer check);
- the side-photo checks on real side photos (only the front path was run on a real photo, the CC0 fixture);
- that a crop or kurta hem visibly changes a render (the one check used a short shirt, so the hem barely moved);
- the new screens on a phone.

**Owner actions (outside the code):** buy the domain; create the Cloudflare account, named tunnel and Pages project; create the Expo/EAS account; write the privacy policy text; read NVIDIA's SegFormer licence (https://github.com/NVlabs/SegFormer/blob/master/LICENSE) to confirm the non-commercial assumption in LQ11.

### §4.2b Garment isolation design (decided 2026-11-27)

**Root cause (verified):**
- `services/garment_cutout.py` uses MediaPipe Selfie Multiclass, whose only garment label is "clothes", and keeps every clothes pixel.
- `product_link_service._json_ld_product` takes `image[0]`, which is usually the model shot.
- The page title is stored as `source_title` but never used to choose a target.

**Pipeline:**
1. **Pick the photo (LQ2).** Collect all product images: the JSON-LD `image` list plus every `og:image`, up to about 6, each fetched through the SSRF-safe fetcher from 4.2. Use the first image with no person in it (MediaPipe person check). Segment only when every image shows a person.
2. **Pick the target (LQ1).** Infer the category from the title, JSON-LD `category` and breadcrumbs (for example "sweater" → Top, "jeans" → Bottom). The import sheet pre-selects it, and the user confirms or changes it with one tap.
3. **Segment (LQ3, LQ8, LQ9).** SegFormer-B2 Clothes (`mattmdjaga/segformer_b2_clothes`, `model.safetensors` 109 MB, 27.4M parameters, 18 ATR labels). It runs in the **API process**, loads lazily, unloads after 10 idle minutes, and counts against the 2-concurrent image limit (2.1) and the step-3 memory measurement (about 0.3–0.5 GB resident). It's added to `training/download_tryon_models.py` with a pinned revision and SHA-256. Label mapping:

   | Category | Labels kept |
   |---|---|
   | Top | Upper-clothes |
   | Outerwear | Upper-clothes (known limitation: a jacket over a tee comes out as both) |
   | Bottom | Pants or Skirt, whichever is larger |
   | Dress | Dress; if none is found, offer Upper-clothes + Skirt/Pants as a "co-ord / set" candidate |
   | Footwear | Left-shoe + Right-shoe |
   | Accessory | The largest of Bag, Hat, Scarf, Belt, Sunglasses |

   Candidates covering less than 2% of the image are dropped.
4. **Preview → confirm (LQ4, LQ7).**
   - `POST /wardrobe/import-link/preview` (and an upload equivalent) returns `preview_id`, the suggested category, the candidate cut-outs and the original photo.
   - The app shows three choices: **Looks right** / **Pick a different piece** / **Use the original photo**.
   - `POST /wardrobe/imports/{preview_id}/confirm` with `{choice, category}` creates the item.
   - Unconfirmed previews and their temporary files expire after **1 hour**.
5. **Classify (LQ6).** The CNN runs on the chosen cut-out. If its category disagrees with the user's, **the user's category wins**: the CNN's subcategory and colour are kept, and the item is flagged `needs_review`.
6. **Scope (LQ5).** The same flow replaces the old cut-out for **camera uploads** and the **"Remove model from photo"** action (`POST /wardrobe/{id}/remove-model`). The MediaPipe "keep all clothes" cut-out in `garment_cutout.py` is **deleted, with no dual path**. **ISNet stays**, because it does a different job: background removal for flat-lay garments in try-on.
7. **Licence (LQ11).** The model's licence is "other", pointing to the NVlabs SegFormer licence, which is believed to be non-commercial. That's accepted for a free, non-commercial release. Record it in `training/FASHION_DATASET_LICENSE_AUDIT.md`. Revisit, for example by switching to a commercially licensed hosted API such as Ximilar, if AURA ever makes money.
8. **Tests.**
   - A fixture model photo (sweater + jeans) where the Top choice yields an Upper-clothes-only cut-out.
   - Flat-lay preference on a page with mixed images.
   - Preview expiry.
   - The user's category winning over the CNN's.
   - `importorskip` for torch and transformers.
9. **Release fallback (LQ10).** If SegFormer integration slips, release with steps 1, 2 and 4 only. The preview's "Use the original photo" option stops wrong cut-outs from being saved silently.

### §4.11 Virtual Look fit design (decided 2026-11-27)

**What the code does today (verified):**
- `body_analysis.analyze_proportions` measures **pixel** widths of the front-photo silhouette and turns them into ratios that drive the body-shape label. Nothing is in cm, `heightCm` is not used as a scale, and the side photo isn't measured. The output says "not a body measurement".
- `clothing_items` has **no size** field.
- The CatVTON try-on mask (`tryon_mask`) follows the clothes currently worn in the avatar photo, so a new garment takes the old garment's shape, with no notion of size, ease or length.
- Nothing is 3D.

**Build order (VQ1):** measurements → size advice → fit visuals in 2D try-on. A true 3D avatar is a stretch goal (5.11).

1. **Measurements (VQ2–VQ5, VQ13).**
   - **Inputs:** height is **required** as the scale reference; weight is optional.
   - **Method:** front photo for widths and side photo for depths, both measured with the existing MediaPipe pose and segmentation models (no new model, no extra memory). Each width and depth pair is treated as an ellipse to get chest, waist and hip circumferences.
   - **Output:** chest, waist, hip, shoulder width, inseam and arm length in cm, each with a ± range.
   - **Capture:** a guide with a silhouette overlay asks for fitted clothing, a straight front pose, a clean side pose, the full body in frame and arms slightly away from the body.
   - **Failed checks or low confidence:** don't estimate. Fall back to "enter your own".
   - **Manual entry:** users can type or correct any value. **Manual values always win.** Each value is labelled "estimated" or "measured by you".
   - **Side photo:** deleted as soon as the measurements are computed; only the numbers are kept. The front photo stays as the try-on avatar.
   - Runs in the API process under the 2-concurrent image limit (2.1).
2. **Garment sizes (VQ6, VQ14).**
   - Migration adding to `clothing_items` an optional **size label** (XS–XXL, a waist/length size such as 32/32, or free text) and optional **flat measurements** (chest width, length, waist, inseam).
   - The label is chosen at upload or confirm time (fits the §4.2b preview → confirm step). Link import tries to read the size from the page.
   - A built-in **generic size chart** (India, EU and US sizes, men's and women's) maps a label to body ranges when no flat measurements exist. Brand-specific charts come later.
   - The profile's `topSize` and `bottomSize` are the fallback when the user has no measurements.
3. **Size advice (VQ7, VQ15).**
   - Each zone (chest, waist, hip, length) is rated **tight / snug / regular / relaxed / loose**.
   - Ratings compare body against garment measurements, with an ease allowance for each fit type (slim, regular, oversized) and the user's fit preference.
   - An overall verdict appears on the item detail screen, on **marketplace listings** (computed only for the viewer) and next to try-on results.
   - An "estimated" note appears whenever the advice relies on photo estimates or the generic chart.
   - **Display only in v1:** no change to recommendation scores.
4. **Fit visuals in try-on (VQ8).** CatVTON stays.
   - The mask is built from the **body outline**, not the clothes currently worn.
   - It's widened by the garment's ease.
   - It ends at a hem line computed from the garment's length relative to the user's height (a crop top stops above the waist; a long kurta reaches the knee).
   - Memory use doesn't change.
5. **Privacy (VQ10).** Measurements, height and weight are body data, so the 4.3 rules apply: consent before capture, inclusion in "Delete my body data" and account deletion, never logged, never shown to other users.
6. **Accuracy check before deploying (VQ11).**
   - Tape-measure 5–10 volunteers and compare against the app's estimates.
   - **Target: ±4 cm on chest, waist and hip.**
   - A measurement that misses the target is shown **only as a range** ("roughly 84–92 cm"), never a single number.
   - The results go in the project report.
   - Release goes ahead either way (VQ12).
7. **Tests.**
   - Synthetic silhouette fixtures with known widths and depths, checking the cm output and the ellipse maths.
   - Manual values override estimates.
   - The size chart maps labels to ranges.
   - Zone verdicts at the boundaries of each rating.
   - The side photo is deleted after measuring.
   - The mask's hem position and width change with the garment's length and ease.

---

## Later (behind tests, not blocking release)

| # | Work | Addresses |
|---|---|---|
| 5.1 | Delete the dead LangGraph pipeline, legacy tools and `src/mocks/data.ts`. Drop `langgraph` and `langchain-core` | L1 |
| 5.2 | Remove committed archives and the empty root lockfile | L2 |
| 5.3 | A single `fashion_vocab` module: colours, neutrals, occasion groups (decide whether wedding is formal or its own group) and reward scales | L6 |
| 5.4 | Thin `main.py`: move the photo pipeline, order notifications and the WebSocket loop into services | L17 |
| 5.5 | Fix N+1 queries (seller counts, conversations, renders), add pagination, enable WAL | L7, L8 |
| 5.6 | Versioned migrations in one module, including the try-on tables | L12 |
| 5.7 | Separate dev, runtime and try-on requirement sets, with lock files and pinned model revisions and hashes (base Qwen, try-on). Add ruff and ESLint | L9 |
| 5.8 | Frontend tests (jest-expo): auth store, service mappers, checkout, realtime reconnect | M11 |
| 5.9 | Keep the original photo after a cut-out. Add decay to the bandit's taste memory. Retry a failed outfit-compat load | L21, L20, L10 |
| 5.10 | Optional: EAS Update for over-the-air JS fixes; httpOnly cookies for web if traffic grows; TestFlight or App Store if a native iPhone app is wanted (needs report/block, deletion and a privacy policy, all done in step 4) | — |
| 5.11 | **3D avatar (stretch goal):** a parametric body (SMPL-X or a simpler mannequin) shaped by the user's **measurements**, with no photo fitting and no new ML model. It's rotatable in the app with three.js / `expo-gl`. **No 3D clothing**, because cloth simulation is research-scale. The SMPL-X licence is non-commercial, consistent with LQ11 | VQ9 |

## Dependency graph

```
1.1 green suite ─► 1.4 tests ─┬─► 2.1 ─► 4.8 (upload re-encode)
1.2 logging ──────────────────┼─► 2.7 ─► 2.4 (marketplace holds)
1.3 ranking snapshot ─────────┼─► 2.5 bandit, 2.6 slates, 4.5 chat grounding
1.5 portable paths ───────────┼─► 2.3 try-on worker ─► 3.1–3.2 memory go/no-go
1.6 stable key ───────────────┘                └─► 4.3 privacy / account deletion
2.2 stylist-only chat ─► 3.1
2.1 image limit + 4.2 SSRF fetcher ─► 4.2b garment isolation ─► 3.1 (re-measure memory with SegFormer loaded)
1.5 paths + 2.1 image limit + 4.3 privacy ─► 4.11 Virtual Look fit ─► volunteer accuracy check
4.2b preview/confirm ─► 4.11 (size label chosen at confirm)
4.1–4.8, 4.11 ─► 4.9 APK release, 4.10 web release
```

## Decision log (2026-11-27)

### Machine profiles: 8 GB-safe defaults ("Option A", decided 2026-11-27)

- **Context:** the public host is the owner's 16 GB Mac; teammates test on Macs with as little as 8 GB.
- **Decision:** the code's defaults and `.env.example` are the 8 GB profile: `AURA_TRYON_ENABLED=0`, `AURA_PRELOAD_VISION=0`. The host sets both to `1` in its own `.env`. Everything except try-on works on 8 GB. Try-on says "turned off on this server" rather than giving a slow, poor result. The README section "Which settings for my Mac?" tells everyone who clones the repo.
- **Not changed:** SegFormer and ISNet stay in short-lived child processes (cheap, and safe on both machines); chat keeps one model (`AURA_CHAT_USE_STYLIST=1`).
- **Safeguards:** the server logs a warning at startup when the try-on models are installed but try-on is off, so a host missing its `.env` lines is noticed. Tests set `AURA_TRYON_ENABLED=1` in `tests/conftest.py`, so try-on stays tested.
- **Rollback to "Option B" (everything on by default)**, if testing shows Option A works badly:
  1. In `Capstone_Agents/settings.py`, change the default `"0"` to `"1"` for `AURA_TRYON_ENABLED` and `AURA_PRELOAD_VISION` (both are marked with a comment).
  2. In `Capstone_Agents/.env.example`, set both to `1` and reword the "MACHINE PROFILE" block to tell 8 GB testers to set `AURA_TRYON_ENABLED=0` if their Mac struggles.
  3. In `README.md` "Which settings for my Mac?", swap which row is the default.
  4. The host's `.env` needs no change. The app message and startup warning still apply. No other code depends on the defaults.
- **Revisit when:** a teammate measures try-on on an 8 GB Mac (`/health` → `resources`), or testers report that "off" gets in their way.

| Q | Question | Decision |
|---|---|---|
| Q1 | Deployment target | Public: APK + web, anyone can install |
| Q1a | Backend host | The developer's Mac behind a tunnel |
| Q1b | Sign-up | Open to anyone |
| Q1c | Scale | 50–100 users |
| Q2 | Product stance | Ongoing product, demo-breaking items first |
| Q3 | Hardware limit | 8 GB is a hard limit |
| Q4 | Event-loop blocking | `def` routes + CNN pre-loaded + concurrency cap of 2 |
| Q5 | Chat grounding | Validate → regenerate once → deterministic fallback |
| Q6 | Bandit | Fix N+1 queries, whole-wardrobe load and lost updates now |
| Q7 | Tunnel | Cloudflare named tunnel on an owned domain |
| Q8 | Chat model | Fine-tuned stylist 1.5B for chat and picking |
| Q9 | Try-on | Separate process + per-user, daily and global limits + 7-day retention |
| Q10 | Body data | Consent, delete body data, minimise parsing data, delete account, privacy policy |
| Q11 | Link import | Proper SSRF fix, or turn import off for release |
| Q12 | Abuse | Rate limits as listed. No email verification in v1 |
| Q13 | Uptime | Accept downtime when the Mac sleeps. No launchd |
| Q14 | Portability | Mac now. Design for an Oracle free ARM VM (try-on off) |
| Q15 | Worker start | API spawns the try-on worker as a child process |
| Q16 | Order holds | Auto-cancel after 72 h; at most 3 open orders per buyer |
| Q17 | Android | `com.aurastylist.app`, EAS Build APK, EAS-managed key, GitHub Releases |
| Q18 | Logs | INFO to a rotating file; only WARNING+ in the terminal |
| Q19 | Order | Foundations → stop freezes and limit work → measure memory → harden, then ship |
| Q20 | iPhone | Web app; Android gets APK + web |
| Q21 | Web hosting | Cloudflare Pages at `app.yourdomain.com` |
| Q22 | Web token | `localStorage` + 7-day web sessions + CSP + log out everywhere |
| — | Report / block | Added to step 4 (4.4) |

### Link-import garment isolation (2026-11-27)

| Q | Question | Decision |
|---|---|---|
| LQ1 | How the target garment is known | Inferred from the title, JSON-LD and breadcrumbs, then confirmed by the user on the import sheet |
| LQ2 | Which photo to use | The first product image with no person; segment only if every image shows a person |
| LQ3 | Segmentation model | SegFormer-B2 Clothes (local). Consider SCHP-LIP only if jacket imports turn out to be common |
| LQ4 | Confirmation | Always preview: Looks right / Pick a different piece / Use the original photo |
| LQ5 | Scope | Also camera uploads and "Remove model". Delete the old MediaPipe cut-out with no dual path; keep ISNet for try-on flat lays |
| LQ6 | User vs. CNN category | The user wins; the item is flagged `needs_review` |
| LQ7 | API shape | Preview → confirm, with a 1-hour expiry |
| LQ8 | Where SegFormer runs | The API process: lazy load, 10-minute idle unload, shares the 2-concurrent limit |
| LQ9 | Label mapping | As in the §4.2b table, with a 2% minimum area |
| LQ10 | Plan placement | Step 4.2b; not a release blocker |
| LQ11 | Licence | Accept non-commercial terms for a free release; record it; revisit if AURA is monetised |

### Virtual Look fit (2026-11-27)

| Q | Question | Decision |
|---|---|---|
| VQ1 | What to build first | Measurements → size advice → 2D fit visuals → 3D avatar (stretch) |
| VQ2 | Scale reference | Height required; weight optional |
| VQ3 | Manual measurements | Allowed; they always override estimates; each value labelled estimated or measured by you |
| VQ4 | Estimation method | Front and side photos with MediaPipe, scaled by height, ellipse circumferences; no SMPL-X fitting and no hosted API |
| VQ5 | Photo rules | Capture guide with overlay; refuse to estimate when the checks fail |
| VQ6 | Garment sizes | Optional label + optional flat measurements + a generic IN/EU/US size chart; size read from imported pages |
| VQ7 | Advice format | Per-zone tight → loose ratings with ease and fit preference; shown on item detail, listings (viewer only) and try-on |
| VQ8 | Try-on fit | Mask from the body outline, widened by ease, hem from the garment's length; CatVTON kept |
| VQ9 | 3D avatar | "Later" (5.11): measurement-driven, no 3D clothing |
| VQ10 | Privacy | Measurements are body data under the 4.3 rules |
| VQ11 | Accuracy | Volunteer tape-measure check before deploying, target ±4 cm; ranges only if missed |
| VQ12 | Plan placement | Step 4.11; the accuracy check gates the measurement claims, not the release |
| VQ13 | Side photo | Deleted after the measurements are computed |
| VQ14 | Profile sizes | `topSize` / `bottomSize` are the fallback for advice |
| VQ15 | Ranking | Size advice is display only in v1 |
