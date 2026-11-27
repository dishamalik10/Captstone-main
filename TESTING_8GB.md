# Testing AURA on an 8 GB Mac

Read this if you are testing on an **8 GB Mac**. The public host is the owner's 16 GB Mac. Your job is to confirm that everything works on the smallest supported machine, and to report memory numbers so the team can tune the settings.

The settings decision is **"Option A"**: try-on is off by default, and only the host turns it on. If testing shows Option A works badly, the team switches back to "Option B". The steps for that are in the ENGINEERING_PLAN decision log, under "Machine profiles".

## 0. Setup (once)

1. Follow the README "Setup guide" steps 1–5. Keep `Capstone_Agents/.env` as copied from `.env.example`; it already has the 8 GB settings:
   ```
   AURA_TRYON_ENABLED=0
   AURA_PRELOAD_VISION=0
   ```
   Also set `AURA_MEDIA_SIGNING_KEY` (README step 2).
2. Start the server **without** `--reload`. Close other heavy apps.
3. Run the machine check and keep its output for your report:
   ```bash
   cd Capstone_Agents && source .venv/bin/activate
   python -m scripts.machine_check
   ```
   It should say `"profile": "8 GB tester"` and `"Settings suit this machine."`.

## 1. Feature checks (try-on off)

For each check, note **pass/fail**, **how long it took**, and anything odd.

| # | What to do | Expected |
|---|---|---|
| 1 | Sign up, log in, log out, log in again | Works. A wrong password five times gets "too many attempts" |
| 2 | Add a wardrobe photo (the first one after starting the server) | A preview appears. The first upload is a few seconds slower (the garment model loads then); later ones are faster |
| 3 | Add a photo of someone wearing a top and jeans | The preview offers a cut-out of just the top or the jeans; "Pick a different piece" works |
| 4 | Import a shop product link | A preview appears, with a size filled in if the shop page names one |
| 5 | Item detail: add a size (for example M) and, optionally, flat measurements | Saved; "How it should fit you" appears once you have measurements or a usual size in your profile |
| 6 | Get outfit recommendations for two occasions | Outfits appear within a few seconds |
| 7 | Chat with the stylist: ask for an outfit for a wedding | A reply in 10–20 s; it names only clothes you own |
| 8 | My Virtual Look: add a front photo (consent screen first) | The avatar and body-shape analysis appear |
| 9 | My Virtual Look → Body measurements: enter your height, then add a side photo | Estimates are shown as ranges ("roughly …"), or a clear reason why not (for example arms too close to the body) |
| 10 | Type your own chest/waist/hip | They replace the estimates and are labelled "measured by you" |
| 11 | Press "Try it on" on an outfit | **Expected on 8 GB:** "Try-on is turned off on this server". Not an error, not a spinner |
| 12 | Marketplace: list an item, open someone else's listing | "Will it fit you?" shows on others' listings, not on yours |
| 13 | Message a seller; report a listing; block a user | Messages arrive live; blocked users disappear from the feed and the marketplace |
| 14 | Privacy → "Delete my body data" | Photos, measurements and height are gone (check Body measurements) |

## 2. Memory under load

While the server runs, do checks 2, 6 and 7 back to back, then run:

```bash
python -m scripts.machine_check --server
```

Record:
- `server_resources.api_peak_rss_mb`;
- `swap_used_gb`;
- Activity Monitor → Memory → "Memory Pressure" colour (green / yellow / red).

**Concerns:** red pressure, more than 3 GB of swap, or a chat reply slower than 30 s.

## 3. Optional: try-on on 8 GB

Only if you have time. This tells the team whether Option A is too cautious.

1. Download the try-on models (README step 3), set `AURA_TRYON_ENABLED=1` in `.env`, close everything else, and restart the server.
2. Render **one** outfit. Note how long it takes and the memory pressure colour during the render.
3. Run `python -m scripts.machine_check --server` straight after it finishes.
4. Set `AURA_TRYON_ENABLED=0` again afterwards.

The 8 GB budget from ENGINEERING_PLAN step 3 is about 6.5 GB combined (API + try-on worker) without heavy swap. The 16 GB host measured about 6.0 GB.

## 4. What to send back

Send this to the team (no screenshots of personal photos, please):

```
Machine check output (step 0):  <paste>
Feature checks 1–14:            <pass/fail + time + notes for each>
Memory under load (step 2):     peak RSS ___ MB, swap ___ GB, pressure ___
Try-on on 8 GB (optional):      render time ___, pressure ___, worker peak ___ MB
Anything that felt slow or broken:
```

**How the team uses it:**
- **Switch to Option B (try-on on by default):** if several testers render try-on on 8 GB with green or yellow pressure and acceptable times.
- **Lower a limit, or move a model to a child process:** if any check shows red pressure with try-on off. That would be a bug in Option A.
