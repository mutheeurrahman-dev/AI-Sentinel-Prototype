"""
build_db.py
-----------
Runs the full detection pipeline over the CSVs in data/ and populates
data/sentinel.db:
  1. Load projects.csv, submissions.csv
  2. Run financial anomaly engine -> per-project financial_risk_score + reasons
  3. Run image verification over every submission -> visual_risk_score + reasons
  4. Combine into overall_risk_score / risk_level per project
  5. Write everything into SQLite (projects, submissions, flags tables)

Run once after seed_data.py + generate_mock_images.py:
    python build_db.py
"""

import csv
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))

from app.database import init_db, get_connection
from app.financial_engine import run_financial_engine, risk_level
from app.image_verification import verify_submission

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
PHOTO_DIR = os.path.join(os.path.dirname(__file__), "uploads", "photos")
RECEIPT_DIR = os.path.join(os.path.dirname(__file__), "uploads", "receipts")

# Weighting for combining financial + visual signals into one overall score.
# Financial data (hard numbers) is weighted slightly higher than visual
# evidence (which can be more ambiguous), but both matter.
FINANCIAL_WEIGHT = 0.6
VISUAL_WEIGHT = 0.4


def main():
    t0 = time.time()
    with open(os.path.join(DATA_DIR, "projects.csv")) as f:
        projects = list(csv.DictReader(f))
    with open(os.path.join(DATA_DIR, "submissions.csv")) as f:
        submissions = list(csv.DictReader(f))

    print(f"Loaded {len(projects)} projects, {len(submissions)} submissions")

    print("Running financial anomaly engine...")
    financial_results = run_financial_engine(projects)

    print("Running image/receipt verification (this can take a minute)...")
    projects_by_id = {p["project_id"]: p for p in projects}
    hash_store: dict = {}
    visual_results = {}
    project_visual_scores: dict[str, list[float]] = {}

    for i, sub in enumerate(submissions):
        project = projects_by_id.get(sub["project_id"])
        if not project:
            continue
        photo_path = os.path.join(PHOTO_DIR, sub["photo_filename"])
        receipt_path = os.path.join(RECEIPT_DIR, sub["receipt_filename"])
        result = verify_submission(sub, project, photo_path, receipt_path, hash_store)
        visual_results[sub["submission_id"]] = result
        project_visual_scores.setdefault(sub["project_id"], []).append(result.visual_risk_score)
        if (i + 1) % 200 == 0:
            print(f"  ...{i + 1}/{len(submissions)} submissions verified")

    init_db(reset=True)
    conn = get_connection()
    cur = conn.cursor()

    for p in projects:
        pid = p["project_id"]
        fin = financial_results.get(pid)
        visual_scores = project_visual_scores.get(pid, [])
        # A project's visual risk = the worst (max) submission score, since
        # a single fabricated/mismatched submission is enough to warrant review.
        visual_score = max(visual_scores) if visual_scores else 0.0
        financial_score = fin.risk_score if fin else 0.0
        overall = round(financial_score * FINANCIAL_WEIGHT + visual_score * VISUAL_WEIGHT, 1)

        cur.execute(
            """INSERT OR REPLACE INTO projects
               (project_id, category, state, district, mp_name, sanctioned_cost, actual_cost,
                sanction_date, expected_completion_date, actual_completion_date, status,
                implementing_agency, financial_risk_score, visual_risk_score, overall_risk_score, risk_level)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (pid, p["category"], p["state"], p["district"], p["mp_name"],
             float(p["sanctioned_cost"]), float(p["actual_cost"]), p["sanction_date"],
             p["expected_completion_date"], p["actual_completion_date"] or None, p["status"],
             p["implementing_agency"], financial_score, visual_score, overall, risk_level(overall)),
        )

        if fin:
            for reason in fin.reasons:
                if "No financial anomalies" not in reason:
                    cur.execute(
                        "INSERT INTO flags (project_id, submission_id, flag_source, reason) VALUES (?,?,?,?)",
                        (pid, None, "financial", reason),
                    )

    for sub in submissions:
        vr = visual_results.get(sub["submission_id"])
        cur.execute(
            """INSERT OR REPLACE INTO submissions
               (submission_id, project_id, progress_percent_claimed, photo_filename,
                receipt_filename, submission_date, visual_risk_score)
               VALUES (?,?,?,?,?,?,?)""",
            (sub["submission_id"], sub["project_id"], float(sub["progress_percent_claimed"]),
             sub["photo_filename"], sub["receipt_filename"], sub["submission_date"],
             vr.visual_risk_score if vr else 0.0),
        )
        if vr:
            for reason in vr.reasons:
                if "No visual" not in reason:
                    cur.execute(
                        "INSERT INTO flags (project_id, submission_id, flag_source, reason) VALUES (?,?,?,?)",
                        (sub["project_id"], sub["submission_id"], "visual", reason),
                    )

    conn.commit()
    conn.close()

    elapsed = time.time() - t0
    print(f"Done in {elapsed:.1f}s. Database written to data/sentinel.db")


if __name__ == "__main__":
    main()
