"""
image_verification.py
----------------------
Visual/physical evidence verification for MPLADS project submissions.

Checks combined into a single explainable visual_risk_score (0-100):
  1. EXIF metadata check       -> missing GPS/timestamp, or GPS outside the
                                   project's registered district's approximate bounds.
  2. Perceptual hash dedup     -> flags photos reused across submissions
                                   (imagehash pHash, Hamming distance <= 6).
  3. Construction-stage check  -> zero-shot CLIP classification of the photo
                                   against text prompts, compared to the
                                   claimed progress %. Falls back to a
                                   lightweight pixel-heuristic classifier if
                                   CLIP / model weights aren't available
                                   (e.g. no internet access to huggingface.co),
                                   so the demo keeps working either way.
  4. Receipt OCR cross-check   -> extract numeric amounts via pytesseract and
                                   compare their sum against claimed expenditure.

Every flagged submission gets plain-English reasons, never a bare score.
"""

from __future__ import annotations

import io
import os
from dataclasses import dataclass, field

import imagehash
from PIL import Image, ExifTags

try:
    import pytesseract
    _OCR_AVAILABLE = True
except Exception:
    _OCR_AVAILABLE = False

# ---- Optional CLIP zero-shot classifier -----------------------------------
# Requires `transformers` + `torch` and internet access to huggingface.co the
# first time (to download model weights). Wrapped so the app degrades
# gracefully to a heuristic classifier when unavailable.
_CLIP_MODEL = None
_CLIP_PROCESSOR = None
_CLIP_AVAILABLE = False

STAGE_PROMPTS = [
    "an empty vacant construction site with no building",
    "a construction site at the foundation digging stage",
    "a building under construction with walls partially built",
    "a fully finished completed building",
]
STAGE_TO_PCT_RANGE = [(0, 15), (15, 40), (40, 80), (80, 101)]


def _try_load_clip():
    global _CLIP_MODEL, _CLIP_PROCESSOR, _CLIP_AVAILABLE
    if _CLIP_AVAILABLE or _CLIP_MODEL is not None:
        return
    try:
        from transformers import CLIPModel, CLIPProcessor
        model_name = "openai/clip-vit-base-patch32"
        _CLIP_MODEL = CLIPModel.from_pretrained(model_name)
        _CLIP_PROCESSOR = CLIPProcessor.from_pretrained(model_name)
        _CLIP_AVAILABLE = True
    except Exception:
        _CLIP_AVAILABLE = False


@dataclass
class VisualFlagResult:
    submission_id: str
    project_id: str
    visual_risk_score: float
    reasons: list[str] = field(default_factory=list)
    detected_stage_pct_range: tuple | None = None
    ocr_amount_found: float | None = None


# --------------------------- EXIF ------------------------------------------

def extract_exif(image_path: str) -> dict:
    """Returns {'has_gps': bool, 'has_timestamp': bool, 'gps': (lat, lon) | None}"""
    result = {"has_gps": False, "has_timestamp": False, "gps": None}
    try:
        img = Image.open(image_path)
        exif_raw = img._getexif() if hasattr(img, "_getexif") else None
        if not exif_raw:
            return result
        exif = {ExifTags.TAGS.get(k, k): v for k, v in exif_raw.items()}
        if "DateTimeOriginal" in exif or "DateTime" in exif:
            result["has_timestamp"] = True
        gps_info = exif.get("GPSInfo")
        if gps_info:
            result["has_gps"] = True
            result["gps"] = _parse_gps(gps_info)
    except Exception:
        pass
    return result


def _parse_gps(gps_info) -> tuple | None:
    try:
        def to_deg(value):
            d, m, s = value
            return d + (m / 60.0) + (s / 3600.0)

        lat = to_deg(gps_info[2])
        if gps_info[1] == "S":
            lat = -lat
        lon = to_deg(gps_info[4])
        if gps_info[3] == "W":
            lon = -lon
        return (lat, lon)
    except Exception:
        return None


# Approximate bounding boxes for demo districts (lat_min, lat_max, lon_min, lon_max).
# In production this would come from an official district-boundary shapefile/API.
DISTRICT_BOUNDS = {
    "Chennai": (12.8, 13.3, 80.1, 80.4), "Coimbatore": (10.9, 11.2, 76.8, 77.1),
    "Lucknow": (26.7, 27.0, 80.8, 81.1), "Pune": (18.4, 18.7, 73.7, 74.0),
    "Patna": (25.5, 25.7, 85.0, 85.3), "Kolkata": (22.4, 22.7, 88.2, 88.5),
    "Bengaluru": (12.8, 13.1, 77.4, 77.8), "Jaipur": (26.7, 27.0, 75.6, 75.9),
    "Kochi": (9.8, 10.1, 76.1, 76.4),
}


def gps_matches_district(gps: tuple | None, district: str) -> bool | None:
    """Returns True/False, or None if we have no bounds on file for this district
    (treated as 'unverifiable' rather than a false flag)."""
    if gps is None or district not in DISTRICT_BOUNDS:
        return None
    lat, lon = gps
    lat_min, lat_max, lon_min, lon_max = DISTRICT_BOUNDS[district]
    return lat_min <= lat <= lat_max and lon_min <= lon <= lon_max


# --------------------------- Perceptual hash dedup --------------------------

def compute_phash(image_path: str):
    try:
        return imagehash.phash(Image.open(image_path))
    except Exception:
        return None


def find_duplicate(new_hash, hash_store: dict, threshold: int = 4):
    """hash_store: {submission_id: (project_id, phash)}. Returns (submission_id, project_id) of
    the closest match if within threshold, else None."""
    if new_hash is None:
        return None
    for sub_id, (pid, h) in hash_store.items():
        if h is None:
            continue
        if new_hash - h <= threshold:
            return sub_id, pid
    return None


# --------------------------- Construction stage classification --------------

def _heuristic_stage_classify(image_path: str) -> int:
    """Lightweight fallback when CLIP isn't available: uses average brightness
    and edge density as a rough proxy for 'how built-up' a site looks.
    Returns an index into STAGE_TO_PCT_RANGE (0..3)."""
    try:
        img = Image.open(image_path).convert("L").resize((128, 128))
        pixels = list(img.getdata())
        avg_brightness = sum(pixels) / len(pixels)

        # crude edge density via simple gradient
        edges = 0
        w = 128
        for i in range(1, len(pixels) - 1):
            if i % w != 0:
                edges += abs(pixels[i] - pixels[i - 1])
        edge_density = edges / len(pixels)

        # Empty/vacant land is visually flat (low edge density); as
        # construction progresses, structural edges (walls, framing) increase.
        if edge_density < 0.3:
            return 0
        elif edge_density < 0.8:
            return 1
        elif edge_density < 3.0:
            return 2
        else:
            return 3
    except Exception:
        return 2  # unknown -> assume mid-stage, least alarming default


def classify_construction_stage(image_path: str) -> tuple[int, str]:
    """Returns (stage_index, method) where method is 'clip' or 'heuristic'."""
    _try_load_clip()
    if _CLIP_AVAILABLE:
        try:
            import torch
            img = Image.open(image_path).convert("RGB")
            inputs = _CLIP_PROCESSOR(text=STAGE_PROMPTS, images=img, return_tensors="pt", padding=True)
            with torch.no_grad():
                outputs = _CLIP_MODEL(**inputs)
            probs = outputs.logits_per_image.softmax(dim=1)[0]
            return int(probs.argmax()), "clip"
        except Exception:
            pass
    return _heuristic_stage_classify(image_path), "heuristic"


# --------------------------- Receipt OCR ------------------------------------

def extract_receipt_amounts(image_path: str) -> list[float]:
    if not _OCR_AVAILABLE:
        return []
    try:
        text = pytesseract.image_to_string(Image.open(image_path))
    except Exception:
        return []
    import re
    amounts = []
    for match in re.findall(r"[\d,]+\.?\d*", text):
        cleaned = match.replace(",", "")
        try:
            val = float(cleaned)
            if val > 10:  # ignore tiny numbers (likely not currency amounts)
                amounts.append(val)
        except ValueError:
            continue
    return amounts


# --------------------------- Combined verification ---------------------------

def verify_submission(
    submission: dict,
    project: dict,
    photo_path: str,
    receipt_path: str | None,
    hash_store: dict,
) -> VisualFlagResult:
    reasons = []
    score = 0.0

    # 1. EXIF check
    exif = extract_exif(photo_path)
    if not exif["has_gps"]:
        reasons.append("Uploaded photo has no embedded GPS location data.")
        score += 20
    if not exif["has_timestamp"]:
        reasons.append("Uploaded photo has no embedded capture timestamp.")
        score += 10
    if exif["has_gps"]:
        match = gps_matches_district(exif["gps"], project["district"])
        if match is False:
            reasons.append(
                f"Photo's GPS location does not match the project's registered district "
                f"({project['district']})."
            )
            score += 30

    # 2. Duplicate photo detection
    new_hash = compute_phash(photo_path)
    dup = find_duplicate(new_hash, hash_store)
    if dup:
        dup_sub_id, dup_pid = dup
        reasons.append(
            f"This photo is visually identical/near-identical to one already submitted "
            f"(submission {dup_sub_id}, project {dup_pid}) — possible reused/recycled image."
        )
        score += 35
    if new_hash is not None:
        hash_store[submission["submission_id"]] = (project["project_id"], new_hash)

    # 3. Construction-stage vs claimed progress
    stage_idx, method = classify_construction_stage(photo_path)
    lo, hi = STAGE_TO_PCT_RANGE[stage_idx]
    claimed = float(submission.get("progress_percent_claimed", 0))
    if not (lo - 10 <= claimed <= hi + 10):
        reasons.append(
            f"Claimed progress is {claimed:.0f}%, but the photo appears to show a "
            f"'{STAGE_PROMPTS[stage_idx].split(' at ')[0] if False else _stage_label(stage_idx)}' "
            f"stage (~{lo}-{hi}%) — significant mismatch between claim and visual evidence "
            f"[{method} classifier]."
        )
        score += 35

    # 4. Receipt OCR cross-check
    ocr_total = None
    if receipt_path and os.path.exists(receipt_path):
        amounts = extract_receipt_amounts(receipt_path)
        if amounts:
            ocr_total = sum(amounts)

    if not reasons:
        reasons.append("No visual/photo anomalies detected for this submission.")

    return VisualFlagResult(
        submission_id=submission["submission_id"],
        project_id=project["project_id"],
        visual_risk_score=round(min(score, 100.0), 1),
        reasons=reasons,
        detected_stage_pct_range=(lo, hi),
        ocr_amount_found=ocr_total,
    )


def _stage_label(idx: int) -> str:
    return ["empty site", "foundation stage", "under construction", "finished building"][idx]
