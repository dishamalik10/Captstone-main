"""Full-body photo -> personal avatar, approximate body proportions and try-on masks.

Models (local, Apache 2.0): MediaPipe Pose Landmarker (33 body landmarks) and the
MediaPipe Selfie Multiclass segmenter (background / hair / body skin / face skin /
clothes / other). Both run on the CPU in about a second.

The "avatar" is the user's own photo, framed 3:4 on a neutral studio backdrop. It is
not a generated or reshaped body, so proportions, skin tone and appearance are the
user's own. Every measurement here is a 2D estimate from one front photo: clothing,
pose, camera angle and lens distortion all shift it, so results are reported as
approximate ratios with a confidence level, never as body measurements in cm.
"""
from __future__ import annotations

import math
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageFilter, ImageOps

from settings import settings

# MediaPipe Selfie Multiclass categories.
BACKGROUND, HAIR, BODY_SKIN, FACE_SKIN, CLOTHES, OTHER = range(6)
# MediaPipe Pose landmark indices.
NOSE, L_SHOULDER, R_SHOULDER, L_ELBOW, R_ELBOW, L_WRIST, R_WRIST = 0, 11, 12, 13, 14, 15, 16
L_HIP, R_HIP, L_KNEE, R_KNEE, L_ANKLE, R_ANKLE = 23, 24, 25, 26, 27, 28
HAND_POINTS = (17, 18, 19, 20, 21, 22)
FOOT_POINTS = (29, 30, 31, 32)

AVATAR_SIZE = (768, 1024)  # 3:4, width x height
BACKDROP = (236, 233, 227)
MIN_PHOTO_HEIGHT = 480


class BodyPhotoError(ValueError):
    """The photo cannot be used; the message is safe to show to the user."""


@dataclass
class ParsedPhoto:
    image: Image.Image            # RGB
    parsing: np.ndarray           # HxW uint8 category map
    landmarks: np.ndarray         # 33x3 (x px, y px, visibility)


class _Models:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.pose = None
        self.segmenter = None

    def missing(self) -> list[str]:
        names = ("pose_landmarker_full.task", "selfie_multiclass_256x256.tflite")
        return [name for name in names if not (settings.tryon_model_dir / name).is_file()]

    def load(self):
        with self._lock:
            if self.pose is None:
                missing = self.missing()
                if missing:
                    raise FileNotFoundError(
                        "Body analysis models are missing: " + ", ".join(missing)
                        + ". Run `python -m training.download_tryon_models`."
                    )
                from mediapipe.tasks.python import BaseOptions, vision

                root = settings.tryon_model_dir
                self.pose = vision.PoseLandmarker.create_from_options(vision.PoseLandmarkerOptions(
                    base_options=BaseOptions(model_asset_path=str(root / "pose_landmarker_full.task")),
                    running_mode=vision.RunningMode.IMAGE,
                    num_poses=2,
                    min_pose_detection_confidence=0.5,
                ))
                self.segmenter = vision.ImageSegmenter.create_from_options(vision.ImageSegmenterOptions(
                    base_options=BaseOptions(model_asset_path=str(root / "selfie_multiclass_256x256.tflite")),
                    running_mode=vision.RunningMode.IMAGE,
                    output_category_mask=True,
                ))
        return self.pose, self.segmenter


_models = _Models()


def models_ready() -> bool:
    return not _models.missing()


def _mp_image(image: Image.Image):
    import mediapipe as mp

    return mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(np.asarray(image.convert("RGB"))))


def parse_photo(image: Image.Image) -> ParsedPhoto:
    """Segment the person and detect pose landmarks (pixel coordinates)."""
    pose, segmenter = _models.load()
    image = image.convert("RGB")
    mp_image = _mp_image(image)
    with _models._lock:
        pose_result = pose.detect(mp_image)
        seg_result = segmenter.segment(mp_image)
    if not pose_result.pose_landmarks:
        raise BodyPhotoError("No person was found. Use a clear, well-lit photo of one person, head to feet.")
    if len(pose_result.pose_landmarks) > 1:
        raise BodyPhotoError("More than one person is in the photo. Use a photo of just you.")
    width, height = image.size
    landmarks = np.array(
        [[p.x * width, p.y * height, p.visibility if p.visibility is not None else 1.0]
         for p in pose_result.pose_landmarks[0]],
        dtype=np.float32,
    )
    parsing = np.asarray(seg_result.category_mask.numpy_view(), dtype=np.uint8).copy()
    parsing = parsing.reshape(parsing.shape[:2])  # MediaPipe returns HxWx1
    if parsing.shape != (height, width):
        parsing = np.asarray(Image.fromarray(parsing).resize((width, height), Image.NEAREST))
    return ParsedPhoto(image=image, parsing=parsing, landmarks=landmarks)


def _visible(landmarks: np.ndarray, *indexes: int, threshold: float = 0.5) -> bool:
    return all(landmarks[i, 2] >= threshold for i in indexes)


def validate(parsed: ParsedPhoto) -> list[str]:
    """Raise for unusable photos; return softer warnings for usable ones."""
    lm = parsed.landmarks
    width, height = parsed.image.size
    if height < MIN_PHOTO_HEIGHT:
        raise BodyPhotoError(f"The photo is too small ({width}x{height}). Use one at least {MIN_PHOTO_HEIGHT}px tall.")
    if not _visible(lm, L_SHOULDER, R_SHOULDER, L_HIP, R_HIP):
        raise BodyPhotoError("Your shoulders and hips need to be clearly visible. Face the camera, full body in frame.")
    if not _visible(lm, L_ANKLE, R_ANKLE, threshold=0.35):
        raise BodyPhotoError("Your feet are cut off. Use a full-body photo from head to feet.")
    person = parsed.parsing != BACKGROUND
    if person.mean() < 0.06:
        raise BodyPhotoError("You are too small in the photo. Stand closer so your body fills most of the frame.")
    warnings = []
    shoulder_span = abs(lm[L_SHOULDER, 0] - lm[R_SHOULDER, 0])
    torso = abs((lm[L_HIP, 1] + lm[R_HIP, 1]) / 2 - (lm[L_SHOULDER, 1] + lm[R_SHOULDER, 1]) / 2)
    if torso and shoulder_span / torso < 0.35:
        warnings.append("You seem to be turned sideways; a straight-on front photo gives better results.")
    hip_left, hip_right = sorted((lm[L_HIP, 0], lm[R_HIP, 0]))
    hip_half = (hip_right - hip_left)
    for wrist in (L_WRIST, R_WRIST):
        if hip_left - hip_half < lm[wrist, 0] < hip_right + hip_half and abs(lm[wrist, 1] - lm[L_HIP, 1]) < torso * 0.35:
            warnings.append("Your arms are close to your body, so waist and hip widths may read wider than they are. "
                            "Holding arms slightly away from the sides helps.")
            break
    return warnings


# -- avatar ---------------------------------------------------------------------------

def keep_person_only(parsing: np.ndarray) -> np.ndarray:
    """Drop segmented blobs that aren't the person (a bag on the floor, a chair).

    Keeps the largest connected region plus any small piece lying inside its bounding
    box (e.g. a detached strand of hair); everything else becomes background."""
    import cv2

    person = (parsing != BACKGROUND).astype(np.uint8)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(person, 8)
    if count <= 2:
        return parsing
    main = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    x, y, w, h = (stats[main, cv2.CC_STAT_LEFT], stats[main, cv2.CC_STAT_TOP],
                  stats[main, cv2.CC_STAT_WIDTH], stats[main, cv2.CC_STAT_HEIGHT])
    keep = np.zeros(count, dtype=bool)
    keep[main] = True
    for label in range(1, count):
        lx, ly, lw, lh = stats[label, :4]
        keep[label] |= lx >= x and ly >= y and lx + lw <= x + w and ly + lh <= y + h
    cleaned = parsing.copy()
    cleaned[~keep[labels]] = BACKGROUND
    return cleaned


def build_avatar(parsed: ParsedPhoto) -> tuple[Image.Image, np.ndarray, np.ndarray]:
    """Frame the person 3:4 on a plain backdrop. Returns (avatar, parsing, landmarks) in avatar space."""
    parsed = ParsedPhoto(image=parsed.image, parsing=keep_person_only(parsed.parsing), landmarks=parsed.landmarks)
    person = parsed.parsing != BACKGROUND
    ys, xs = np.nonzero(person)
    top, bottom = ys.min(), ys.max()
    body_h = bottom - top
    pad = int(body_h * 0.06)
    crop_h = body_h + 2 * pad
    crop_w = int(crop_h * AVATAR_SIZE[0] / AVATAR_SIZE[1])
    centre_x = (xs.min() + xs.max()) / 2
    left = int(round(centre_x - crop_w / 2))
    upper = int(top - pad)
    box = (left, upper, left + crop_w, upper + crop_h)

    # Soft-edged cut-out on the backdrop; the person's pixels are untouched.
    alpha = Image.fromarray((person * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.5))
    backdrop = Image.new("RGB", parsed.image.size, BACKDROP)
    composited = Image.composite(parsed.image, backdrop, alpha)
    avatar = _crop_padded(composited, box, BACKDROP).resize(AVATAR_SIZE, Image.LANCZOS)
    parsing = np.asarray(
        _crop_padded(Image.fromarray(parsed.parsing), box, BACKGROUND).resize(AVATAR_SIZE, Image.NEAREST)
    )
    scale = AVATAR_SIZE[1] / crop_h
    landmarks = parsed.landmarks.copy()
    landmarks[:, 0] = (landmarks[:, 0] - left) * scale
    landmarks[:, 1] = (landmarks[:, 1] - upper) * scale
    return avatar, parsing, landmarks


def _crop_padded(image: Image.Image, box: tuple[int, int, int, int], fill) -> Image.Image:
    left, upper, right, lower = box
    canvas = Image.new(image.mode, (right - left, lower - upper), fill)
    canvas.paste(image, (-left, -upper))
    return canvas


# -- proportions ----------------------------------------------------------------------

def _row_width(body: np.ndarray, y: int, centre_x: float) -> int:
    """Width of the contiguous body run that contains the body's centre line."""
    y = int(np.clip(y, 0, body.shape[0] - 1))
    row = body[y]
    cx = int(np.clip(centre_x, 0, row.size - 1))
    if not row[cx]:
        filled = np.nonzero(row)[0]
        if filled.size == 0:
            return 0
        cx = int(filled[np.argmin(np.abs(filled - cx))])
    left = cx
    while left > 0 and row[left - 1]:
        left -= 1
    right = cx
    while right < row.size - 1 and row[right + 1]:
        right += 1
    return right - left + 1


def _remove_arms(body: np.ndarray, lm: np.ndarray, shoulder_px: float) -> np.ndarray:
    """Erase the arms so hanging arms are not counted as waist or hip width."""
    import cv2

    erased = body.astype(np.uint8).copy()
    thickness = max(3, int(shoulder_px * 0.26))
    for chain in ((L_SHOULDER, L_ELBOW, L_WRIST), (R_SHOULDER, R_ELBOW, R_WRIST)):
        points = [lm[i, :2] for i in chain]
        # Start a little down the upper arm so the shoulder line itself is kept.
        start = points[0] + (points[1] - points[0]) * 0.35
        polyline = np.array([start, points[1], points[2]], dtype=np.int32)
        cv2.polylines(erased, [polyline], False, 0, thickness)
        for hand in HAND_POINTS:
            cv2.circle(erased, tuple(int(v) for v in lm[hand, :2]), thickness // 2, 0, -1)
    return erased.astype(bool)


def analyze_proportions(parsing: np.ndarray, lm: np.ndarray, image: Image.Image, warnings: list[str]) -> dict[str, Any]:
    body = np.isin(parsing, (BODY_SKIN, CLOTHES, OTHER))
    shoulder_y = (lm[L_SHOULDER, 1] + lm[R_SHOULDER, 1]) / 2
    hip_y = (lm[L_HIP, 1] + lm[R_HIP, 1]) / 2
    ankle_y = (lm[L_ANKLE, 1] + lm[R_ANKLE, 1]) / 2
    centre_x = (lm[L_SHOULDER, 0] + lm[R_SHOULDER, 0] + lm[L_HIP, 0] + lm[R_HIP, 0]) / 4
    torso = max(1.0, hip_y - shoulder_y)
    shoulder_joint_span = float(np.hypot(*(lm[L_SHOULDER, :2] - lm[R_SHOULDER, :2])))
    trunk = _remove_arms(body, lm, shoulder_joint_span)

    shoulder = _row_width(body, int(shoulder_y + torso * 0.06), centre_x)
    waist_rows = range(int(shoulder_y + torso * 0.45), int(shoulder_y + torso * 0.85))
    waist_widths = [_row_width(trunk, y, centre_x) for y in waist_rows]
    waist = int(np.percentile(waist_widths, 10)) if waist_widths else 0
    hip_rows = range(int(hip_y - torso * 0.05), int(hip_y + torso * 0.30))
    hip_widths = [_row_width(trunk, y, centre_x) for y in hip_rows]
    hip = int(np.percentile(hip_widths, 90)) if hip_widths else 0
    if min(shoulder, waist, hip) <= 0:
        raise BodyPhotoError("Your outline could not be measured. Use a photo with a plain background and good light.")

    ratios = {
        "shoulder_to_hip": round(shoulder / hip, 2),
        "waist_to_hip": round(waist / hip, 2),
        "waist_to_shoulder": round(waist / shoulder, 2),
        "torso_to_leg": round(float(torso / max(1.0, ankle_y - hip_y)), 2),
    }
    shape, reason = classify_shape(ratios)
    confidence = "medium"
    if warnings or min(lm[i, 2] for i in (L_SHOULDER, R_SHOULDER, L_HIP, R_HIP)) < 0.8:
        confidence = "low"
    clothes_share = float((parsing == CLOTHES).sum() / max(1, body.sum()))
    if clothes_share > 0.85:
        warnings.append("Loose or layered clothing hides your outline; fitted clothing gives a better estimate.")
        confidence = "low"
    return {
        "body_shape": shape,
        "body_shape_reason": reason,
        "confidence": confidence,
        "ratios": ratios,
        "silhouette_widths_px": {"shoulder": shoulder, "waist": waist, "hip": hip},
        "torso_length": "long" if ratios["torso_to_leg"] > 0.62 else "short" if ratios["torso_to_leg"] < 0.48 else "balanced",
        "skin_tone": estimate_skin_tone(parsing, image),
        "warnings": warnings,
        "method": "2D front-photo estimate from MediaPipe pose landmarks and body segmentation; "
                  "not a body measurement. Clothing, pose and camera angle affect it.",
    }


def classify_shape(ratios: dict[str, float]) -> tuple[str, str]:
    """Map silhouette width ratios to the app's body-shape options (approximate)."""
    s_h, w_h, w_s = ratios["shoulder_to_hip"], ratios["waist_to_hip"], ratios["waist_to_shoulder"]
    if w_h >= 0.92 and w_s >= 0.88:
        return "apple", "Waist width is close to or above both shoulder and hip width."
    if s_h >= 1.08:
        return "athletic", "Shoulders read wider than hips (inverted-triangle silhouette)."
    if s_h <= 0.92:
        return "pear", "Hips read wider than shoulders."
    if w_h <= 0.78 and w_s <= 0.78:
        return "hourglass", "Shoulders and hips are balanced with a clearly narrower waist."
    return "rectangle", "Shoulders, waist and hips are fairly similar in width."


def estimate_skin_tone(parsing: np.ndarray, image: Image.Image) -> dict[str, Any] | None:
    """Approximate skin depth from face/body skin pixels via the Individual Typology Angle."""
    skin = np.isin(parsing, (FACE_SKIN, BODY_SKIN))
    if skin.sum() < 200:
        return None
    rgb = np.asarray(image.convert("RGB"), dtype=np.float32)[skin] / 255.0
    median = np.median(rgb, axis=0)
    L, a, b = _rgb_to_lab(median)
    ita = math.degrees(math.atan2(L - 50.0, b if b != 0 else 1e-6))
    if ita > 55:
        tone = "fair"
    elif ita > 41:
        tone = "light"
    elif ita > 28:
        tone = "medium"
    elif ita > 10:
        tone = "tan"
    else:
        tone = "deep"
    return {
        "tone": tone,
        "ita_degrees": round(ita, 1),
        "sample_hex": "#" + "".join(f"{int(round(c * 255)):02X}" for c in median),
        "note": "Approximate; lighting and white balance change it. Undertone (e.g. olive) is not inferred.",
    }


def _rgb_to_lab(rgb: np.ndarray) -> tuple[float, float, float]:
    def linear(c):
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (linear(float(c)) for c in rgb)
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883

    def f(t):
        return t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116

    fx, fy, fz = f(x), f(y), f(z)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


# -- try-on masks ---------------------------------------------------------------------

GARMENT_REGION = {"Top": "upper", "Outerwear": "upper", "Bottom": "lower", "Dress": "overall"}


@dataclass(frozen=True)
class MaskFit:
    """How a garment's size changes its try-on mask (4.11, VQ8); see services/tryon_fit.py.

    ``hem_y``: where the garment ends (avatar pixel row), from its length; None keeps the
    default extent. ``widen_px``: extra width on each side for a roomier cut."""
    hem_y: float | None = None
    widen_px: int = 0


def tryon_mask(parsing: np.ndarray, lm: np.ndarray, region: str, fit: MaskFit | None = None) -> Image.Image:
    """Region the try-on model may repaint: generous around the garment area, never the face, hair or feet.

    Without ``fit`` the mask follows the body and the clothes in the photo. With it, the
    garment's hem and width follow its size (a crop top stops above the waist, a kurta
    reaches the knee, an oversized cut is wider)."""
    import cv2

    height, width = parsing.shape
    person = parsing != BACKGROUND
    shoulder_y = (lm[L_SHOULDER, 1] + lm[R_SHOULDER, 1]) / 2
    hip_y = (lm[L_HIP, 1] + lm[R_HIP, 1]) / 2
    knee_y = (lm[L_KNEE, 1] + lm[R_KNEE, 1]) / 2
    ankle_y = (lm[L_ANKLE, 1] + lm[R_ANKLE, 1]) / 2
    torso = max(1.0, hip_y - shoulder_y)
    clothes_or_skin = np.isin(parsing, (BODY_SKIN, CLOTHES, OTHER))
    rows = np.arange(height)[:, None]

    def band(top: float, bottom: float) -> np.ndarray:
        return (rows >= top) & (rows <= bottom)

    def row_fill(mask: np.ndarray) -> np.ndarray:
        filled = mask.copy()
        for y in np.nonzero(mask.any(axis=1))[0]:
            xs = np.nonzero(mask[y])[0]
            filled[y, xs.min():xs.max() + 1] = True
        return filled

    hem = None if fit is None or fit.hem_y is None else float(np.clip(fit.hem_y, shoulder_y + torso * 0.4, ankle_y))
    shoulder_span = float(np.hypot(*(lm[L_SHOULDER, :2] - lm[R_SHOULDER, :2])))
    mask = np.zeros_like(person)
    if region in {"upper", "overall"}:
        upper_bottom = hip_y + torso * 0.15
        if region == "upper" and hem is not None:
            upper_bottom = hem + torso * 0.03
        upper = clothes_or_skin & band(shoulder_y - torso * 0.12, min(upper_bottom, hip_y + torso * 0.15))
        mask |= row_fill(upper & band(shoulder_y, min(upper_bottom, hip_y + torso * 0.15))) | upper
        if region == "upper" and hem is not None:
            no_arms = _remove_arms(clothes_or_skin, lm, shoulder_span)
            if upper_bottom > hip_y + torso * 0.15:
                # A long top (kurta, longline coat) also covers the hips and thighs.
                mask |= row_fill(no_arms & band(hip_y + torso * 0.15, upper_bottom))
            else:
                # A short top: the photo's own top below the new hem must be repainted too.
                mask |= (parsing == CLOTHES) & no_arms & band(upper_bottom, hip_y + torso * 0.15)
    if region in {"lower", "overall"}:
        lower_top = shoulder_y + torso * (0.55 if region == "lower" else 0.3)
        # Arms hang beside the hips: erase them so a skirt change does not repaint the forearms.
        legs_and_hips = _remove_arms(clothes_or_skin, lm, shoulder_span)
        lower_bottom = ankle_y if hem is None else min(ankle_y, hem + torso * 0.03)
        lower = legs_and_hips & band(lower_top, lower_bottom)
        # Existing clothes below the waist must be repainted too (e.g. jeans -> skirt).
        lower |= (parsing == CLOTHES) & legs_and_hips & band(lower_top, height)
        # Bound sideways to hips/legs plus room for a flared skirt, so arm remnants cannot widen it.
        leg_x = lm[[L_HIP, R_HIP, L_KNEE, R_KNEE, L_ANKLE, R_ANKLE], 0]
        hip_span = abs(lm[L_HIP, 0] - lm[R_HIP, 0])
        columns = np.arange(width)[None, :]
        within = (columns >= leg_x.min() - hip_span * 0.75) & (columns <= leg_x.max() + hip_span * 0.75)
        mask |= row_fill(lower & within) & within
    if region == "overall":
        mask |= (parsing == CLOTHES) & band(shoulder_y - torso * 0.12, knee_y + torso)

    mask_u8 = mask.astype(np.uint8) * 255
    if fit is not None and fit.widen_px > 0:
        # A roomier cut: widen sideways below the shoulders (never up into the neck).
        widened = cv2.dilate(mask_u8, np.ones((1, 2 * int(fit.widen_px) + 1), np.uint8))
        below = rows[:, 0] >= shoulder_y
        mask_u8[below] = widened[below]
    # Generous growth: any sliver of the old garment left at the mask edge gets extended by the model.
    grow = max(3, int(height * 0.03)) | 1
    mask_u8 = cv2.dilate(mask_u8, np.ones((grow, grow), np.uint8))

    # Protect face, hair, hands and feet.
    protect = np.isin(parsing, (HAIR, FACE_SKIN)).astype(np.uint8) * 255
    protect = cv2.dilate(protect, np.ones((5, 5), np.uint8))
    radius = max(4, int(height * 0.025))
    for index in HAND_POINTS + FOOT_POINTS:
        if lm[index, 2] >= 0.3:
            cv2.circle(protect, (int(lm[index, 0]), int(lm[index, 1])), radius, 255, -1)
    protect[int(min(height - 1, ankle_y + torso * 0.05)):, :] = 255
    mask_u8[protect > 0] = 0
    return Image.fromarray(mask_u8)


def garment_colour_lab(garment: Image.Image) -> np.ndarray | None:
    """Median Lab colour of a garment cut out on white (None if nothing is left)."""
    import cv2

    rgb = np.asarray(garment.convert("RGB"))
    fabric = np.abs(rgb.astype(np.int16) - 255).sum(axis=2) > 40
    if fabric.sum() < 50:
        return None
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
    return np.median(lab[fabric], axis=0)


def leftover_bottom(
    original: Image.Image, parsing: np.ndarray, lm: np.ndarray, painted: np.ndarray,
    rendered: Image.Image | None = None, new_colour: np.ndarray | None = None,
) -> np.ndarray:
    """Pixels of the photo's *old* trousers/skirt that a lower-garment render did not repaint.

    The lower mask deliberately skips the hanging arms and the feet, so when the new
    bottom is shorter (trousers -> shorts) slivers of the old one survive beside the hands
    and over the ankles. They're found by colour: clothing below the hips that matches
    the old bottom, sampled on the legs between the hips and knees, away from the arms.

    The model also tends to *continue* the old fabric next to protected areas (it sees it
    as context), so when the new garment's colour is clearly different, rendered pixels
    that still look like the old bottom count as leftovers too."""
    import cv2

    height, width = parsing.shape
    hip_y = (lm[L_HIP, 1] + lm[R_HIP, 1]) / 2
    knee_y = (lm[L_KNEE, 1] + lm[R_KNEE, 1]) / 2
    shoulder_y = (lm[L_SHOULDER, 1] + lm[R_SHOULDER, 1]) / 2
    torso = max(1.0, hip_y - shoulder_y)
    centre_x = (lm[L_HIP, 0] + lm[R_HIP, 0]) / 2
    half = abs(lm[L_HIP, 0] - lm[R_HIP, 0]) * 0.45
    rows_, cols = np.arange(height)[:, None], np.arange(width)[None, :]
    clothes = parsing == CLOTHES
    sample = clothes & (rows_ >= hip_y + torso * 0.1) & (rows_ <= knee_y) & (np.abs(cols - centre_x) <= half)
    if sample.sum() < 50:
        return np.zeros_like(clothes)
    lab = cv2.cvtColor(np.asarray(original.convert("RGB")), cv2.COLOR_RGB2LAB).astype(np.float32)
    reference = np.median(lab[sample], axis=0)
    similar = np.linalg.norm(lab - reference, axis=2) < 32  # tolerant of folds and shading
    stale = ~painted
    if rendered is not None and new_colour is not None and np.linalg.norm(new_colour - reference) > 40:
        out = cv2.cvtColor(np.asarray(rendered.convert("RGB")), cv2.COLOR_RGB2LAB).astype(np.float32)
        stale = stale | (np.linalg.norm(out - reference, axis=2) < 32)
    leftover = clothes & similar & (rows_ >= hip_y) & stale
    return cv2.dilate(leftover.astype(np.uint8), np.ones((9, 9), np.uint8)) > 0


def remove_leftover(image: Image.Image, leftover: np.ndarray, lm: np.ndarray) -> Image.Image:
    """Fill leftover pixels. Below the knees each column continues the colour just above
    the gap (the shin over a leg, the backdrop between legs), which keeps ankles clean;
    smaller slivers higher up (beside the hands) are inpainted from their surroundings."""
    import cv2

    if not leftover.any():
        return image
    pixels = np.asarray(image.convert("RGB")).copy()
    knee_y = int((lm[L_KNEE, 1] + lm[R_KNEE, 1]) / 2)
    low = leftover.copy()
    low[:knee_y] = False
    for x in np.nonzero(low.any(axis=0))[0]:
        ys = np.nonzero(low[:, x])[0]
        top = int(ys.min())
        above = top - 1
        while above > knee_y and leftover[above, x]:
            above -= 1
        if above <= 0:
            continue
        # Average a few pixels above so one stray pixel doesn't streak down the column.
        colour = pixels[max(0, above - 6):above + 1, x].mean(axis=0)
        pixels[ys, x] = colour.astype(np.uint8)
    # Soften the vertical streaks, then inpaint the rest (above the knees) and the seams.
    blurred = cv2.GaussianBlur(pixels, (0, 0), 2.0)
    pixels[low] = blurred[low]
    seams = (cv2.dilate(low.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0) & ~low
    rest = (leftover & ~low) | seams
    filled = cv2.inpaint(pixels, rest.astype(np.uint8) * 255, 9, cv2.INPAINT_TELEA)
    return Image.fromarray(filled)


# -- garment cut-out ------------------------------------------------------------------

class _GarmentCutter:
    """ISNet background removal for flat-lay garment photos (onnxruntime, CPU)."""

    def __init__(self) -> None:
        self._session = None
        self._lock = threading.Lock()

    @property
    def path(self) -> Path:
        return settings.tryon_model_dir / "isnet-general-use.onnx"

    def available(self) -> bool:
        return self.path.is_file()

    def cut(self, image: Image.Image) -> Image.Image:
        """Garment on white, cropped to the garment. Falls back to the photo if no model."""
        image = ImageOps.exif_transpose(image).convert("RGB")
        if not self.available():
            return image
        import onnxruntime as ort

        with self._lock:
            if self._session is None:
                self._session = ort.InferenceSession(str(self.path), providers=["CPUExecutionProvider"])
            resized = np.asarray(image.resize((1024, 1024), Image.LANCZOS), dtype=np.float32) / 255.0
            tensor = ((resized - 0.5) / 1.0).transpose(2, 0, 1)[None].astype(np.float32)
            output = self._session.run(None, {self._session.get_inputs()[0].name: tensor})[0][0, 0]
        low, high = float(output.min()), float(output.max())
        alpha = (output - low) / max(1e-6, high - low)
        alpha_img = Image.fromarray((alpha * 255).astype(np.uint8)).resize(image.size, Image.LANCZOS)
        alpha_arr = np.asarray(alpha_img)
        ys, xs = np.nonzero(alpha_arr > 128)
        if ys.size < 0.02 * alpha_arr.size:  # nothing confidently segmented
            return image
        white = Image.new("RGB", image.size, (255, 255, 255))
        cut = Image.composite(image, white, alpha_img)
        pad = int(0.04 * max(image.size))
        box = (max(0, xs.min() - pad), max(0, ys.min() - pad),
               min(image.width, xs.max() + pad), min(image.height, ys.max() + pad))
        return cut.crop(box)


garment_cutter = _GarmentCutter()
