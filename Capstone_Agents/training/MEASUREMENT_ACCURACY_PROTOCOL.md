# Measurement accuracy check (ENGINEERING_PLAN 4.11, VQ11)

**Goal:** find out whether the photo estimates of chest, waist and hip are within **±4 cm** of a tape measure. The release does not wait for this check (VQ12). It decides how the app *shows* each measurement:

- **Passes:** shown as a single number.
- **Fails, or not yet checked:** shown only as a range ("roughly 84–92 cm").

## Volunteers

- **How many:** 5–10 adults, with a mix of heights and builds.
- **Consent:** each volunteer agrees in writing that they are measured and photographed for this check. They also agree that the photos are deleted at the end.
- **Records:** record no names; use V1, V2, …
- **Accounts:** use a test account per volunteer. Afterwards, use **Delete my body data**, or delete the account.

## Tape measurements (do these first)

Measure over light, fitted clothing, standing relaxed, breathing out normally. The tape should be level and snug, but not pulling.

| Zone | Where |
|---|---|
| chest | Fullest part of the chest, under the armpits |
| waist | Narrowest part of the torso (or at the navel if there is no narrowing) |
| hip | Fullest part of the seat |
| inseam (optional) | Crotch to floor, barefoot |
| height | Barefoot, against a wall |

## Photos in the app

1. Open **My Virtual Look**.
2. Take the **front** photo, following the guide:
   - fitted clothing;
   - plain background;
   - full body, head to feet;
   - feet slightly apart;
   - arms held a little away from the body;
   - camera at waist height, about 2.5–3 m away.
3. In **Body measurements**, enter the tape-measured height.
4. Take the **side** photo with the same setup, standing side-on to the camera.
5. Write down each estimate the app shows. If the app shows a range, take the middle of the range. If the app says it could not estimate, write that down too; it counts as a failure of the capture, not of the maths.

## Recording and scoring

Fill a CSV in this format:

```
volunteer,zone,tape_cm,app_cm
V1,chest,94,97.2
V1,waist,80,83.0
```

Then run:

```
python -m scripts.measurement_accuracy results.csv
```

**The rule for each zone:**
- mean absolute error ≤ 4 cm;
- ≥ 80% of volunteers within ±4 cm;
- at least 5 volunteers.

**Where the result goes:** the summary is written to `training/measurement_accuracy_results.json`. The app reads that file straight away; no restart is needed.

**Afterwards:**
1. Delete the CSV.
2. Delete the volunteers' body data.
3. Add the summary table, and the mean signed error (does the app read high or low?), to the project report.

**If a zone is consistently high or low:** do not "fix" it with a correction factor tuned on the same 5–10 people. Record it as a finding.
