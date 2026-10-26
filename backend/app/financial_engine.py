"""
financial_engine.py
--------------------
Financial anomaly detection for MPLADS projects.

Two layers, combined into a single explainable risk_score (0-100):
  1. Rule-based flags   -> cost/duration beyond 2.5 standard deviations of the
                            category (and category+district) norm.
  2. ML layer           -> Isolation Forest over
                            [cost, duration, category_encoded, district_encoded, cost_per_day]
                            to catch subtler, multi-feature anomalies the rules miss.

Every flagged project gets a list of plain-English reason strings -- never a
bare number.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import LabelEncoder

RULE_SD_THRESHOLD = 2.5


@dataclass
class FinancialFlagResult:
    project_id: str
    risk_score: float  # 0-100
    reasons: list[str] = field(default_factory=list)
    rule_flags: list[str] = field(default_factory=list)
    ml_anomaly: bool = False
    ml_score: float = 0.0


def _duration_days(row) -> float | None:
    if not row.get("actual_completion_date"):
        return None
    sanction = pd.to_datetime(row["sanction_date"])
    completion = pd.to_datetime(row["actual_completion_date"])
    return max((completion - sanction).days, 1)


def _prepare_dataframe(projects: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(projects)
    df["sanctioned_cost"] = df["sanctioned_cost"].astype(float)
    df["actual_cost"] = df["actual_cost"].astype(float)
    df["duration_days"] = df.apply(_duration_days, axis=1)
    # For projects without a completion date (in_progress/stalled), estimate
    # elapsed duration so far so the model still has a usable feature.
    today = pd.Timestamp.today()
    elapsed = (today - pd.to_datetime(df["sanction_date"])).dt.days
    df["duration_days"] = df["duration_days"].fillna(elapsed)
    df["cost_ratio"] = df["actual_cost"] / df["sanctioned_cost"].replace(0, np.nan)
    df["cost_per_day"] = df["actual_cost"] / df["duration_days"].replace(0, np.nan)
    df["cost_per_day"] = df["cost_per_day"].fillna(0)
    return df


def _category_stats(df: pd.DataFrame) -> pd.DataFrame:
    stats = df.groupby("category").agg(
        cost_mean=("actual_cost", "mean"),
        cost_std=("actual_cost", "std"),
        duration_mean=("duration_days", "mean"),
        duration_std=("duration_days", "std"),
    ).fillna(0)
    return stats


def _district_stats(df: pd.DataFrame) -> pd.DataFrame:
    stats = df.groupby(["category", "district"]).agg(
        cost_mean=("actual_cost", "mean"),
        cost_std=("actual_cost", "std"),
    ).fillna(0)
    return stats


def _rule_based_flags(row, cat_stats, dist_stats) -> tuple[list[str], list[str]]:
    reasons = []
    flags = []
    cat = row["category"]
    cmean, cstd = cat_stats.loc[cat, ["cost_mean", "cost_std"]]
    dmean, dstd = cat_stats.loc[cat, ["duration_mean", "duration_std"]]

    if cstd and cstd > 0:
        z_cost = (row["actual_cost"] - cmean) / cstd
        if z_cost > RULE_SD_THRESHOLD:
            ratio = row["actual_cost"] / cmean if cmean else 0
            reasons.append(
                f"Cost is {ratio:.1f}x higher than the average for '{cat}' projects "
                f"nationally (₹{row['actual_cost']:,.0f} vs ₹{cmean:,.0f} avg)."
            )
            flags.append("cost_outlier_category")

    try:
        dcmean, dcstd = dist_stats.loc[(cat, row["district"]), ["cost_mean", "cost_std"]]
        if dcstd and dcstd > 0:
            z_cost_d = (row["actual_cost"] - dcmean) / dcstd
            if z_cost_d > RULE_SD_THRESHOLD:
                ratio = row["actual_cost"] / dcmean if dcmean else 0
                reasons.append(
                    f"Cost is {ratio:.1f}x higher than average for '{cat}' projects "
                    f"in {row['district']} district specifically."
                )
                flags.append("cost_outlier_district")
    except KeyError:
        pass

    if dstd and dstd > 0:
        z_dur = (row["duration_days"] - dmean) / dstd
        if z_dur > RULE_SD_THRESHOLD:
            reasons.append(
                f"Completion took {row['duration_days']:.0f} days, far longer than the "
                f"~{dmean:.0f}-day average for '{cat}' projects — possible inefficiency or stalling."
            )
            flags.append("duration_outlier_slow")
        elif z_dur < -RULE_SD_THRESHOLD and row["status"] == "completed":
            reasons.append(
                f"Marked complete in just {row['duration_days']:.0f} days, far faster than the "
                f"~{dmean:.0f}-day average for '{cat}' projects — unusually quick completion."
            )
            flags.append("duration_outlier_fast")

    if row["status"] == "stalled":
        reasons.append("Project status is 'stalled' with no recent progress update.")
        flags.append("stalled")

    return reasons, flags


def _detect_duplicates(df: pd.DataFrame) -> dict[str, list[str]]:
    """Flag near-identical entries: same category/district/agency and cost within 3%."""
    dup_reasons: dict[str, list[str]] = {}
    key_cols = ["category", "district", "implementing_agency"]
    for _, group in df.groupby(key_cols):
        if len(group) < 2:
            continue
        costs = group["sanctioned_cost"].values
        ids = group["project_id"].values
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                if costs[i] == 0:
                    continue
                pct_diff = abs(costs[i] - costs[j]) / costs[i]
                if pct_diff < 0.03:
                    for a, b in [(ids[i], ids[j]), (ids[j], ids[i])]:
                        dup_reasons.setdefault(a, []).append(
                            f"Near-identical to project {b} (same category, district, and agency; "
                            f"sanctioned cost within {pct_diff*100:.1f}%) — possible duplicate claim."
                        )
    return dup_reasons


def run_financial_engine(projects: list[dict]) -> dict[str, FinancialFlagResult]:
    """
    projects: list of dicts with keys matching the projects table.
    Returns: dict[project_id] -> FinancialFlagResult
    """
    if not projects:
        return {}

    df = _prepare_dataframe(projects)
    cat_stats = _category_stats(df)
    dist_stats = _district_stats(df)
    dup_reasons = _detect_duplicates(df)

    # --- ML layer: Isolation Forest ---
    cat_encoder = LabelEncoder()
    dist_encoder = LabelEncoder()
    df["category_encoded"] = cat_encoder.fit_transform(df["category"])
    df["district_encoded"] = dist_encoder.fit_transform(df["district"])

    feature_cols = ["actual_cost", "duration_days", "category_encoded", "district_encoded", "cost_per_day"]
    X = df[feature_cols].fillna(0).values

    iso = IsolationForest(n_estimators=200, contamination=0.13, random_state=42)
    iso.fit(X)
    raw_scores = iso.decision_function(X)  # higher = more normal
    predictions = iso.predict(X)  # -1 = anomaly, 1 = normal

    # Normalize raw_scores to a 0-100 "ML anomaly intensity" (invert so higher = more anomalous)
    min_s, max_s = raw_scores.min(), raw_scores.max()
    span = (max_s - min_s) or 1.0
    ml_intensity = (max_s - raw_scores) / span * 100  # 0 (normal) .. 100 (anomalous)

    results: dict[str, FinancialFlagResult] = {}

    for idx, row in df.iterrows():
        pid = row["project_id"]
        reasons, rule_flags = _rule_based_flags(row, cat_stats, dist_stats)

        if pid in dup_reasons:
            reasons.extend(dup_reasons[pid])
            rule_flags.append("duplicate_suspected")

        is_ml_anomaly = predictions[idx] == -1
        ml_score = float(ml_intensity[idx])
        if is_ml_anomaly:
            reasons.append(
                "Flagged by the anomaly-detection model based on an unusual combination of "
                "cost, duration, category, and location — not explained by a single rule alone."
            )

        # Combine into a final 0-100 risk score:
        #   - each rule flag contributes a fixed weight
        #   - ML intensity contributes proportionally, capped
        rule_weight = min(len(rule_flags) * 22, 66)
        ml_weight = min(ml_score * 0.45, 45) if is_ml_anomaly else ml_score * 0.15
        risk_score = min(100.0, rule_weight + ml_weight)

        if not reasons:
            reasons.append("No financial anomalies detected; cost and timeline are within normal range.")

        results[pid] = FinancialFlagResult(
            project_id=pid,
            risk_score=round(risk_score, 1),
            reasons=reasons,
            rule_flags=rule_flags,
            ml_anomaly=bool(is_ml_anomaly),
            ml_score=round(ml_score, 1),
        )

    return results


def risk_level(score: float) -> str:
    if score >= 60:
        return "high"
    if score >= 30:
        return "medium"
    return "low"
