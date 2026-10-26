"""
seed_data.py
------------
Generates a realistic simulated MPLADS dataset for the AI Sentinel prototype.

Creates two CSVs under backend/data/:
  - projects.csv     : 300-500 MPLADS projects, ~10-15% with injected anomalies
  - submissions.csv  : mock progress submissions (photo/receipt metadata) per project

Run:
    python seed_data.py
"""

import csv
import os
import random
import uuid
from datetime import date, timedelta

from faker import Faker

fake = Faker("en_IN")
random.seed(42)
Faker.seed(42)

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
os.makedirs(DATA_DIR, exist_ok=True)

N_PROJECTS = 420
ANOMALY_RATE = 0.13  # ~13% of records get an injected anomaly

CATEGORIES = ["road", "hand_pump", "school", "community_hall", "sanitation"]

# Rough per-category baseline cost (INR) and typical duration (days) --
# used both to generate "normal" data and to compute deviation stats later.
CATEGORY_BASELINE = {
    "road": {"cost": 3_500_000, "cost_sd": 900_000, "duration": 120, "duration_sd": 30},
    "hand_pump": {"cost": 45_000, "cost_sd": 10_000, "duration": 15, "duration_sd": 5},
    "school": {"cost": 2_200_000, "cost_sd": 500_000, "duration": 180, "duration_sd": 40},
    "community_hall": {"cost": 1_800_000, "cost_sd": 400_000, "duration": 150, "duration_sd": 35},
    "sanitation": {"cost": 300_000, "cost_sd": 70_000, "duration": 45, "duration_sd": 15},
}

STATES_DISTRICTS = {
    "Tamil Nadu": ["Chennai", "Coimbatore", "Madurai", "Salem", "Tiruchirappalli"],
    "Uttar Pradesh": ["Lucknow", "Kanpur", "Varanasi", "Agra", "Meerut"],
    "Maharashtra": ["Pune", "Nagpur", "Nashik", "Aurangabad", "Thane"],
    "Bihar": ["Patna", "Gaya", "Bhagalpur", "Muzaffarpur"],
    "West Bengal": ["Kolkata", "Howrah", "Durgapur", "Siliguri"],
    "Karnataka": ["Bengaluru", "Mysuru", "Hubballi", "Mangaluru"],
    "Rajasthan": ["Jaipur", "Jodhpur", "Udaipur", "Kota"],
    "Kerala": ["Thiruvananthapuram", "Kochi", "Kozhikode"],
}

AGENCIES = [
    "PWD Division Office", "District Rural Development Agency", "Zilla Parishad",
    "Municipal Corporation", "State Rural Roads Development Corp",
    "Block Development Office", "Panchayati Raj Engineering Dept",
]

STATUSES = ["completed", "in_progress", "stalled"]


def random_date(start: date, end: date) -> date:
    delta = (end - start).days
    return start + timedelta(days=random.randint(0, max(delta, 0)))


def make_mp_names(n=60):
    return [fake.name() for _ in range(n)]


MP_NAMES = make_mp_names()


def gen_project(idx: int, force_anomaly: str = None):
    category = random.choice(CATEGORIES)
    baseline = CATEGORY_BASELINE[category]
    state = random.choice(list(STATES_DISTRICTS.keys()))
    district = random.choice(STATES_DISTRICTS[state])

    sanctioned_cost = max(5000, int(random.gauss(baseline["cost"], baseline["cost_sd"] * 0.3)))
    duration_planned = max(5, int(random.gauss(baseline["duration"], baseline["duration_sd"] * 0.3)))

    sanction_date = random_date(date(2022, 4, 1), date(2025, 6, 1))
    expected_completion_date = sanction_date + timedelta(days=duration_planned)

    status = random.choices(STATUSES, weights=[0.55, 0.3, 0.15])[0]

    # "Normal" actual cost/duration: small natural variance around plan
    actual_cost = int(sanctioned_cost * random.uniform(0.92, 1.12))
    actual_duration = int(duration_planned * random.uniform(0.85, 1.25))

    anomaly_type = force_anomaly
    if anomaly_type is None and random.random() < ANOMALY_RATE:
        anomaly_type = random.choice([
            "inflated_cost", "too_fast_completion", "stalled_no_update", "duplicate",
        ])

    if anomaly_type == "inflated_cost":
        actual_cost = int(sanctioned_cost * random.uniform(2.0, 5.0))
    elif anomaly_type == "too_fast_completion":
        actual_duration = max(1, int(duration_planned * random.uniform(0.05, 0.2)))
        status = "completed"
    elif anomaly_type == "stalled_no_update":
        status = "stalled"
        actual_duration = None

    if status == "completed" and actual_duration is not None:
        actual_completion_date = sanction_date + timedelta(days=actual_duration)
    else:
        actual_completion_date = None

    if status != "completed":
        actual_cost = int(actual_cost * random.uniform(0.3, 0.9))  # partial spend so far

    project = {
        "project_id": f"MPLADS-{idx:05d}",
        "category": category,
        "state": state,
        "district": district,
        "mp_name": random.choice(MP_NAMES),
        "sanctioned_cost": sanctioned_cost,
        "actual_cost": actual_cost,
        "sanction_date": sanction_date.isoformat(),
        "expected_completion_date": expected_completion_date.isoformat(),
        "actual_completion_date": actual_completion_date.isoformat() if actual_completion_date else "",
        "status": status,
        "implementing_agency": random.choice(AGENCIES),
        "_injected_anomaly": anomaly_type or "",
    }
    return project


def inject_duplicates(projects, n_pairs=15):
    """Pick n_pairs of projects and create a near-identical duplicate entry for each,
    simulating the same work claimed/funded twice under slightly different IDs."""
    duplicates = []
    sample = random.sample(projects, min(n_pairs, len(projects)))
    for p in sample:
        dup = dict(p)
        dup["project_id"] = p["project_id"] + "-D"
        # tiny jitter so it's "near-identical", not byte-identical
        dup["sanctioned_cost"] = int(p["sanctioned_cost"] * random.uniform(0.98, 1.02))
        dup["actual_cost"] = int(p["actual_cost"] * random.uniform(0.98, 1.02))
        dup["_injected_anomaly"] = "duplicate"
        duplicates.append(dup)
    return duplicates


def gen_submissions(projects):
    """Mock submissions table: progress_percent_claimed, photo/receipt filenames, submission_date."""
    rows = []
    stage_photo_names = {
        (0, 20): "empty_site",
        (20, 45): "foundation_stage",
        (45, 75): "under_construction",
        (75, 100): "near_complete",
        (100, 101): "finished_building",
    }

    def stage_for(pct):
        for (lo, hi), name in stage_photo_names.items():
            if lo <= pct < hi:
                return name
        return "finished_building"

    for p in projects:
        n_updates = random.randint(1, 4)
        claimed_progress = 0
        for i in range(n_updates):
            if p["status"] == "completed":
                claimed_progress = 100 if i == n_updates - 1 else min(95, claimed_progress + random.randint(20, 40))
            elif p["status"] == "stalled":
                claimed_progress = min(60, claimed_progress + random.randint(5, 15))
            else:
                claimed_progress = min(90, claimed_progress + random.randint(15, 35))

            # Mismatch injection: for a slice of anomalous projects, claim a stage
            # far ahead of / behind what the photo actually shows.
            actual_visual_stage_pct = claimed_progress
            if p["_injected_anomaly"] in ("too_fast_completion", "inflated_cost") and random.random() < 0.6:
                actual_visual_stage_pct = max(0, claimed_progress - random.randint(40, 70))

            photo_tag = stage_for(actual_visual_stage_pct)
            submission_date = date.fromisoformat(p["sanction_date"]) + timedelta(days=(i + 1) * 20)

            rows.append({
                "submission_id": str(uuid.uuid4())[:8],
                "project_id": p["project_id"],
                "progress_percent_claimed": claimed_progress,
                "photo_filename": f"{p['project_id']}_{photo_tag}_{i}.jpg",
                "receipt_filename": f"{p['project_id']}_receipt_{i}.jpg",
                "submission_date": submission_date.isoformat(),
                "_true_visual_stage_tag": photo_tag,
            })
    return rows


def main():
    projects = [gen_project(i) for i in range(1, N_PROJECTS + 1)]
    projects += inject_duplicates(projects, n_pairs=15)
    random.shuffle(projects)
    # re-sequence display order but keep project_id stable
    submissions = gen_submissions(projects)

    proj_path = os.path.join(DATA_DIR, "projects.csv")
    sub_path = os.path.join(DATA_DIR, "submissions.csv")

    proj_fields = [
        "project_id", "category", "state", "district", "mp_name", "sanctioned_cost",
        "actual_cost", "sanction_date", "expected_completion_date",
        "actual_completion_date", "status", "implementing_agency", "_injected_anomaly",
    ]
    with open(proj_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=proj_fields)
        writer.writeheader()
        writer.writerows(projects)

    sub_fields = [
        "submission_id", "project_id", "progress_percent_claimed", "photo_filename",
        "receipt_filename", "submission_date", "_true_visual_stage_tag",
    ]
    with open(sub_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=sub_fields)
        writer.writeheader()
        writer.writerows(submissions)

    n_anomalous = sum(1 for p in projects if p["_injected_anomaly"])
    print(f"Generated {len(projects)} projects ({n_anomalous} with injected anomalies, "
          f"{n_anomalous/len(projects)*100:.1f}%)")
    print(f"Generated {len(submissions)} submissions")
    print(f"Wrote {proj_path}")
    print(f"Wrote {sub_path}")


if __name__ == "__main__":
    main()
