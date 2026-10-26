"""
main.py -- FastAPI backend for AI Sentinel.

Endpoints:
  GET  /projects                -- list all projects (filterable)
  GET  /projects/{id}           -- full project detail incl. submissions + flags
  GET  /projects/flagged        -- only high/medium risk, sorted by risk score
  POST /submissions             -- submit a new progress update (photo + receipt)
  GET  /stats                   -- summary counts for dashboard
"""

import os
import shutil
import sys
import uuid

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.database import get_connection, init_db
from app.financial_engine import risk_level
from app.image_verification import verify_submission

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
PHOTO_DIR = os.path.join(BASE_DIR, "uploads", "photos")
RECEIPT_DIR = os.path.join(BASE_DIR, "uploads", "receipts")
os.makedirs(PHOTO_DIR, exist_ok=True)
os.makedirs(RECEIPT_DIR, exist_ok=True)

app = FastAPI(title="AI Sentinel API", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/media/photos", StaticFiles(directory=PHOTO_DIR), name="photos")
app.mount("/media/receipts", StaticFiles(directory=RECEIPT_DIR), name="receipts")


@app.on_event("startup")
def startup():
    if not os.path.exists(os.path.join(BASE_DIR, "data", "sentinel.db")):
        init_db()


def _project_row_to_dict(row) -> dict:
    d = dict(row)
    d["risk_level"] = risk_level(d["overall_risk_score"])
    return d


@app.get("/projects")
def list_projects(
    state: str | None = None,
    district: str | None = None,
    category: str | None = None,
    status: str | None = None,
    risk_level_filter: str | None = None,
    q: str | None = None,
    limit: int = 500,
    offset: int = 0,
):
    conn = get_connection()
    query = "SELECT * FROM projects WHERE 1=1"
    params: list = []
    if state:
        query += " AND state = ?"
        params.append(state)
    if district:
        query += " AND district = ?"
        params.append(district)
    if category:
        query += " AND category = ?"
        params.append(category)
    if status:
        query += " AND status = ?"
        params.append(status)
    if q:
        query += " AND (project_id LIKE ? OR mp_name LIKE ? OR implementing_agency LIKE ?)"
        like = f"%{q}%"
        params += [like, like, like]
    query += " ORDER BY overall_risk_score DESC LIMIT ? OFFSET ?"
    params += [limit, offset]

    rows = conn.execute(query, params).fetchall()
    conn.close()
    results = [_project_row_to_dict(r) for r in rows]
    if risk_level_filter:
        results = [r for r in results if r["risk_level"] == risk_level_filter]
    return {"count": len(results), "projects": results}


@app.get("/projects/flagged")
def flagged_projects(min_level: str = "medium", limit: int = 200):
    order = {"low": 0, "medium": 1, "high": 2}
    threshold = order.get(min_level, 1)
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM projects ORDER BY overall_risk_score DESC LIMIT ?", (2000,)
    ).fetchall()
    conn.close()
    results = [_project_row_to_dict(r) for r in rows]
    results = [r for r in results if order.get(r["risk_level"], 0) >= threshold]
    return {"count": len(results[:limit]), "projects": results[:limit]}


@app.get("/projects/{project_id}")
def project_detail(project_id: str):
    conn = get_connection()
    proj = conn.execute("SELECT * FROM projects WHERE project_id = ?", (project_id,)).fetchone()
    if not proj:
        conn.close()
        raise HTTPException(status_code=404, detail="Project not found")

    submissions = conn.execute(
        "SELECT * FROM submissions WHERE project_id = ? ORDER BY submission_date", (project_id,)
    ).fetchall()
    flags = conn.execute(
        "SELECT * FROM flags WHERE project_id = ? ORDER BY flag_source, id", (project_id,)
    ).fetchall()
    conn.close()

    result = _project_row_to_dict(proj)
    result["submissions"] = [dict(s) for s in submissions]
    result["financial_flags"] = [dict(f)["reason"] for f in flags if f["flag_source"] == "financial"]
    result["visual_flags"] = [
        {"submission_id": f["submission_id"], "reason": f["reason"]}
        for f in flags if f["flag_source"] == "visual"
    ]
    return result


@app.get("/stats")
def stats():
    conn = get_connection()
    total = conn.execute("SELECT COUNT(*) c FROM projects").fetchone()["c"]
    rows = conn.execute("SELECT overall_risk_score, state, category, status FROM projects").fetchall()
    conn.close()

    counts = {"high": 0, "medium": 0, "low": 0}
    by_state: dict[str, dict[str, int]] = {}
    by_category: dict[str, int] = {}
    by_status: dict[str, int] = {}

    for r in rows:
        lvl = risk_level(r["overall_risk_score"])
        counts[lvl] += 1
        by_state.setdefault(r["state"], {"high": 0, "medium": 0, "low": 0})
        by_state[r["state"]][lvl] += 1
        by_category[r["category"]] = by_category.get(r["category"], 0) + (1 if lvl != "low" else 0)
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1

    return {
        "total_projects": total,
        "risk_counts": counts,
        "flagged_by_state": [{"state": s, **v} for s, v in sorted(by_state.items())],
        "flagged_by_category": by_category,
        "by_status": by_status,
    }


@app.post("/submissions")
async def create_submission(
    project_id: str = Form(...),
    progress_percent_claimed: float = Form(...),
    submission_date: str = Form(...),
    photo: UploadFile = File(...),
    receipt: UploadFile | None = File(None),
):
    conn = get_connection()
    project = conn.execute("SELECT * FROM projects WHERE project_id = ?", (project_id,)).fetchone()
    if not project:
        conn.close()
        raise HTTPException(status_code=404, detail="Project not found")

    submission_id = str(uuid.uuid4())[:8]
    photo_filename = f"{project_id}_{submission_id}_{photo.filename}"
    photo_path = os.path.join(PHOTO_DIR, photo_filename)
    with open(photo_path, "wb") as f:
        shutil.copyfileobj(photo.file, f)

    receipt_filename = None
    receipt_path = None
    if receipt is not None:
        receipt_filename = f"{project_id}_{submission_id}_{receipt.filename}"
        receipt_path = os.path.join(RECEIPT_DIR, receipt_filename)
        with open(receipt_path, "wb") as f:
            shutil.copyfileobj(receipt.file, f)

    sub_dict = {
        "submission_id": submission_id,
        "project_id": project_id,
        "progress_percent_claimed": progress_percent_claimed,
    }
    # Build an in-memory hash store from existing submission photos for dedup
    # (a production system would persist hashes; fine for a demo-scale DB).
    hash_store: dict = {}
    existing = conn.execute(
        "SELECT submission_id, project_id, photo_filename FROM submissions LIMIT 2000"
    ).fetchall()
    from app.image_verification import compute_phash
    for row in existing:
        p = os.path.join(PHOTO_DIR, row["photo_filename"])
        if os.path.exists(p):
            hash_store[row["submission_id"]] = (row["project_id"], compute_phash(p))

    result = verify_submission(sub_dict, dict(project), photo_path, receipt_path, hash_store)

    conn.execute(
        """INSERT INTO submissions
           (submission_id, project_id, progress_percent_claimed, photo_filename,
            receipt_filename, submission_date, visual_risk_score)
           VALUES (?,?,?,?,?,?,?)""",
        (submission_id, project_id, progress_percent_claimed, photo_filename,
         receipt_filename, submission_date, result.visual_risk_score),
    )
    for reason in result.reasons:
        if "No visual" not in reason:
            conn.execute(
                "INSERT INTO flags (project_id, submission_id, flag_source, reason) VALUES (?,?,?,?)",
                (project_id, submission_id, "visual", reason),
            )

    # Recompute this project's overall risk score (max visual score across all its submissions)
    all_visual = conn.execute(
        "SELECT visual_risk_score FROM submissions WHERE project_id = ?", (project_id,)
    ).fetchall()
    new_visual_score = max((r["visual_risk_score"] for r in all_visual), default=0.0)
    new_overall = round(project["financial_risk_score"] * 0.6 + new_visual_score * 0.4, 1)
    conn.execute(
        "UPDATE projects SET visual_risk_score = ?, overall_risk_score = ?, risk_level = ? WHERE project_id = ?",
        (new_visual_score, new_overall, risk_level(new_overall), project_id),
    )
    conn.commit()
    conn.close()

    return {
        "submission_id": submission_id,
        "visual_risk_score": result.visual_risk_score,
        "reasons": result.reasons,
        "project_overall_risk_score": new_overall,
        "project_risk_level": risk_level(new_overall),
    }
