"""
generate_mock_images.py
------------------------
Creates synthetic demo photo/receipt image files matching the filenames in
submissions.csv, since we don't have access to real MPLADS site photos.

- Photos are drawn differently per construction stage tag (empty_site,
  foundation_stage, under_construction, near_complete, finished_building) so
  the CLIP/heuristic classifier has genuinely different visual content to
  distinguish between stages.
- ~40% of photos get real EXIF GPS + timestamp written in; the rest are left
  without, to exercise the "missing metadata" flag.
- A handful of photos are exact byte-for-byte reused across submissions to
  exercise perceptual-hash duplicate detection.
- Receipt images have a few printed numeric amounts drawn on them for OCR.

Run after seed_data.py:
    python generate_mock_images.py
"""

import csv
import os
import random
import shutil

import piexif
from PIL import Image, ImageDraw, ImageFont

random.seed(7)

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
PHOTO_DIR = os.path.join(os.path.dirname(__file__), "uploads", "photos")
RECEIPT_DIR = os.path.join(os.path.dirname(__file__), "uploads", "receipts")
os.makedirs(PHOTO_DIR, exist_ok=True)
os.makedirs(RECEIPT_DIR, exist_ok=True)

# Approx district centroids (lat, lon) matching image_verification.DISTRICT_BOUNDS
DISTRICT_COORDS = {
    "Chennai": (13.05, 80.25), "Coimbatore": (11.0, 76.95),
    "Lucknow": (26.85, 80.95), "Pune": (18.55, 73.85),
    "Patna": (25.6, 85.15), "Kolkata": (22.55, 88.35),
    "Bengaluru": (12.95, 77.6), "Jaipur": (26.85, 75.75),
    "Kochi": (9.95, 76.25),
}

STAGE_STYLE = {
    "empty_site": {"bg": (194, 178, 128), "shapes": 0, "label": "Vacant plot"},
    "foundation_stage": {"bg": (160, 150, 130), "shapes": 3, "label": "Foundation laid"},
    "under_construction": {"bg": (150, 150, 150), "shapes": 8, "label": "Under construction"},
    "near_complete": {"bg": (170, 170, 175), "shapes": 14, "label": "Near complete"},
    "finished_building": {"bg": (220, 220, 225), "shapes": 20, "label": "Finished building"},
}


def draw_site_photo(stage_tag: str, seed: int) -> Image.Image:
    """Each call with a different seed produces a genuinely distinct-looking
    photo (different framing, jittered colors/shapes) so that perceptual
    hashing only matches photos that are truly reused, not just same-stage.
    Same stage_tag + seed always reproduces the same image (deterministic)."""
    style = STAGE_STYLE.get(stage_tag, STAGE_STYLE["under_construction"])
    rng = random.Random(seed)

    # jitter the whole palette per-photo so same-stage photos aren't near-identical
    bg = tuple(max(0, min(255, c + rng.randint(-25, 25))) for c in style["bg"])
    sky = (rng.randint(120, 180), rng.randint(170, 210), rng.randint(200, 240))
    cam_offset_x = rng.randint(-60, 60)
    cam_offset_y = rng.randint(-20, 20)
    horizon = 160 + rng.randint(-30, 30)

    img = Image.new("RGB", (640, 480), bg)
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, 640, horizon], fill=sky)

    # scattered ground texture, randomized per photo
    for _ in range(rng.randint(60, 120)):
        x, y = rng.randint(0, 640), rng.randint(horizon, 480)
        r = rng.randint(2, 6)
        shade = rng.randint(-30, 10)
        c = tuple(max(0, min(255, v + shade)) for v in bg)
        draw.ellipse([x, y, x + r, y + r], fill=c)

    # "structure" rectangles scaling with construction progress, jittered position/size
    for i in range(style["shapes"]):
        base_x0 = 60 + (i % 6) * 90 + cam_offset_x
        base_y0 = 400 - (i // 6 + 1) * (55 + rng.randint(-8, 8)) + cam_offset_y
        w = 65 + rng.randint(-10, 10)
        x0, y0 = base_x0, base_y0
        x1, y1 = x0 + w, 400 + cam_offset_y
        brick = (110 + rng.randint(-15, 15), 85 + rng.randint(-15, 15), 65 + rng.randint(-15, 15))
        draw.rectangle([x0, y0, x1, y1], fill=brick, outline=(60, 40, 30))

    # a few extra random noise shapes to break up any residual similarity
    for _ in range(rng.randint(3, 9)):
        x, y = rng.randint(0, 640), rng.randint(0, 480)
        w, h = rng.randint(10, 50), rng.randint(10, 50)
        c = tuple(rng.randint(0, 255) for _ in range(3))
        draw.rectangle([x, y, x + w, y + h], fill=c)

    draw.text((10, 10), f"{style['label']} #{seed}", fill=(0, 0, 0))
    return img


def draw_receipt(project_id: str, amount: float, seed: int) -> Image.Image:
    rng = random.Random(seed)
    img = Image.new("RGB", (500, 700), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.text((20, 20), "PAYMENT RECEIPT", fill=(0, 0, 0))
    draw.text((20, 60), f"Project: {project_id}", fill=(0, 0, 0))
    draw.text((20, 90), "Vendor: Local Contractor Pvt Ltd", fill=(0, 0, 0))
    y = 140
    remaining = amount
    n_lines = rng.randint(1, 3)
    for i in range(n_lines):
        line_amt = round(remaining / (n_lines - i), 2) if i < n_lines - 1 else remaining
        remaining -= line_amt
        draw.text((20, y), f"Item {i+1} amount: Rs. {line_amt:,.2f}", fill=(0, 0, 0))
        y += 40
    draw.text((20, y + 20), f"TOTAL: Rs. {amount:,.2f}", fill=(0, 0, 0))
    return img


def add_exif(path: str, lat: float, lon: float, timestamp: str):
    def to_dms(deg):
        d = int(deg)
        m_full = (deg - d) * 60
        m = int(m_full)
        s = (m_full - m) * 60
        return ((d, 1), (m, 1), (int(s * 100), 100))

    gps_ifd = {
        piexif.GPSIFD.GPSLatitudeRef: "N" if lat >= 0 else "S",
        piexif.GPSIFD.GPSLatitude: to_dms(abs(lat)),
        piexif.GPSIFD.GPSLongitudeRef: "E" if lon >= 0 else "W",
        piexif.GPSIFD.GPSLongitude: to_dms(abs(lon)),
    }
    exif_ifd = {piexif.ExifIFD.DateTimeOriginal: timestamp}
    exif_dict = {"0th": {}, "Exif": exif_ifd, "GPS": gps_ifd}
    exif_bytes = piexif.dump(exif_dict)
    piexif.insert(exif_bytes, path)


def main():
    with open(os.path.join(DATA_DIR, "projects.csv")) as f:
        projects = {p["project_id"]: p for p in csv.DictReader(f)}
    with open(os.path.join(DATA_DIR, "submissions.csv")) as f:
        submissions = list(csv.DictReader(f))

    reused_photo_path = None
    n_with_exif = 0
    n_total = 0

    for i, sub in enumerate(submissions):
        project = projects.get(sub["project_id"])
        if not project:
            continue
        stage_tag = sub["_true_visual_stage_tag"]
        photo_path = os.path.join(PHOTO_DIR, sub["photo_filename"])

        # Every ~25th submission: reuse a previous photo file exactly (duplicate test)
        if reused_photo_path and i % 25 == 0:
            shutil.copyfile(reused_photo_path, photo_path)
        else:
            img = draw_site_photo(stage_tag, seed=i)
            img.save(photo_path, "jpeg")
            if i % 7 == 0:
                reused_photo_path = photo_path

        n_total += 1
        # ~55% of photos get real GPS+timestamp matching their district; rest are missing
        if random.random() < 0.55:
            lat, lon = DISTRICT_COORDS.get(project["district"], (20.0, 78.0))
            # small jitter within district
            lat += random.uniform(-0.05, 0.05)
            lon += random.uniform(-0.05, 0.05)
            # occasionally (for anomalous projects) place GPS in a WRONG district on purpose
            if project["_injected_anomaly"] and random.random() < 0.3:
                wrong_district = random.choice([d for d in DISTRICT_COORDS if d != project["district"]])
                lat, lon = DISTRICT_COORDS[wrong_district]
            try:
                add_exif(photo_path, lat, lon, f"{sub['submission_date'].replace('-', ':')} 10:00:00")
                n_with_exif += 1
            except Exception:
                pass

        # Receipt
        receipt_path = os.path.join(RECEIPT_DIR, sub["receipt_filename"])
        claimed_cost = float(project["actual_cost"]) * (float(sub["progress_percent_claimed"]) / 100.0)
        # For a slice of anomalous projects, make the receipt total mismatch on purpose
        receipt_amount = claimed_cost
        if project["_injected_anomaly"] == "inflated_cost" and random.random() < 0.5:
            receipt_amount = claimed_cost * random.uniform(0.3, 0.6)
        img = draw_receipt(project["project_id"], receipt_amount, seed=i + 1000)
        img.save(receipt_path, "jpeg")

    print(f"Generated {n_total} photos ({n_with_exif} with EXIF GPS+timestamp) in {PHOTO_DIR}")
    print(f"Generated {n_total} receipts in {RECEIPT_DIR}")


if __name__ == "__main__":
    main()
