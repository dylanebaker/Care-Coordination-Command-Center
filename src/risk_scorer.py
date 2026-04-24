"""Risk scorer — rule-based at-risk client ranking.

Pure functions with no side effects. Safe to unit-test in isolation.
All inputs are plain pandas DataFrames; no Streamlit dependencies here.
"""

from __future__ import annotations

import pandas as pd

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

STALLED_DAYS = 14          # referral age (days) before it counts as stalled
EXPIRY_WARNING_DAYS = 30   # consent expiry within this window triggers a flag

TIER_THRESHOLDS = {
    "critical": 65,
    "high":     40,
    "medium":   20,
    # < 20 → "low"
}

# Scoring weights — each feature is independent
_WEIGHTS = {
    "bnl_active":        25,
    "bnl_status_active": 10,
    "chronic_homeless":  20,
    "ca_p3":             15,
    "ca_p2":             10,
    "ca_p1":              5,
    "acuity_very_high":  10,
    "acuity_high":        7,
    "lost_contact_90":   15,
    "lost_contact_30":    8,
    "stalled_referral":  10,
    "consent_expiring":   8,
    "has_violation":      5,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def score_clients(
    clients: pd.DataFrame,
    referrals: pd.DataFrame,
    consent: pd.DataFrame,
    violation_client_ids: set[str] | None = None,
    reference_date: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """Return `clients` with appended risk columns, sorted descending by risk_score.

    Added columns:
      risk_score          int  0–100
      risk_tier           str  critical | high | medium | low
      risk_factors        str  pipe-separated list of fired factors
      days_since_contact  int  NaN if last_contact_date is null
      stalled_referral_count  int
      consent_expiry_days int  NaN if no expiry date; negative = already expired
    """
    today = reference_date if reference_date is not None else pd.Timestamp.today().normalize()

    # Reset the client index so positional iloc alignment works cleanly
    clients = clients.reset_index(drop=True)

    # Working accumulator — keeps client_id aligned with clients.index
    scores = pd.DataFrame({
        "client_id": clients["client_id"],
        "score":     0,
    })

    # ------------------------------------------------------------------
    # 1. BNL / chronic homelessness
    # ------------------------------------------------------------------
    scores.loc[clients["bnl_active_flag"] == True, "score"] += _WEIGHTS["bnl_active"]
    scores.loc[clients["bnl_status"] == "active",   "score"] += _WEIGHTS["bnl_status_active"]
    scores.loc[clients["chronic_homeless_flag"] == True, "score"] += _WEIGHTS["chronic_homeless"]

    # ------------------------------------------------------------------
    # 2. CA priority level  (p1 / p2 / p3)
    # ------------------------------------------------------------------
    ca_map = {"p3": _WEIGHTS["ca_p3"], "p2": _WEIGHTS["ca_p2"], "p1": _WEIGHTS["ca_p1"]}
    scores["score"] += clients["ca_priority_level"].map(ca_map).fillna(0).astype(int)

    # ------------------------------------------------------------------
    # 3. Assessment acuity level
    # ------------------------------------------------------------------
    acuity_map = {
        "very_high": _WEIGHTS["acuity_very_high"],
        "high":      _WEIGHTS["acuity_high"],
    }
    scores["score"] += clients["assessment_acuity_level"].map(acuity_map).fillna(0).astype(int)

    # ------------------------------------------------------------------
    # 4. Days since last contact
    # ------------------------------------------------------------------
    lc = pd.to_datetime(clients["last_contact_date"], errors="coerce")
    days_contact = (today - lc).dt.days
    scores["days_since_contact"] = days_contact.values

    scores.loc[days_contact > 90, "score"]                              += _WEIGHTS["lost_contact_90"]
    scores.loc[(days_contact > 30) & (days_contact <= 90), "score"]    += _WEIGHTS["lost_contact_30"]

    # ------------------------------------------------------------------
    # 5. Stalled referrals (submitted or pending, older than STALLED_DAYS)
    # ------------------------------------------------------------------
    stalled_mask = (
        referrals["status"].isin(["submitted", "pending"]) &
        ((today - referrals["submitted_at"]).dt.days > STALLED_DAYS)
    )
    stalled_counts = (
        referrals[stalled_mask]
        .groupby("client_id")
        .size()
        .rename("stalled_referral_count")
    )
    scores = scores.merge(stalled_counts, on="client_id", how="left")
    scores["stalled_referral_count"] = scores["stalled_referral_count"].fillna(0).astype(int)
    scores.loc[scores["stalled_referral_count"] > 0, "score"] += _WEIGHTS["stalled_referral"]

    # ------------------------------------------------------------------
    # 6. Consent expiry proximity
    # ------------------------------------------------------------------
    consent_expiry = (
        consent[["consent_id", "expiry_date"]]
        .rename(columns={"consent_id": "current_consent_id"})
    )
    exp_merged = (
        clients[["client_id", "current_consent_id"]]
        .merge(consent_expiry, on="current_consent_id", how="left")
    )
    exp_dates = pd.to_datetime(exp_merged["expiry_date"], errors="coerce")
    expiry_days = (exp_dates - today).dt.days
    scores["consent_expiry_days"] = expiry_days.values

    expiring_soon = expiry_days.between(0, EXPIRY_WARNING_DAYS - 1)
    scores.loc[expiring_soon.values, "score"] += _WEIGHTS["consent_expiring"]

    # ------------------------------------------------------------------
    # 7. Has active consent violation
    # ------------------------------------------------------------------
    if violation_client_ids:
        scores.loc[scores["client_id"].isin(violation_client_ids), "score"] += _WEIGHTS["has_violation"]

    # ------------------------------------------------------------------
    # 8. Cap score and assign tier
    # ------------------------------------------------------------------
    scores["risk_score"] = scores["score"].clip(upper=100)
    scores["risk_tier"] = pd.cut(
        scores["risk_score"],
        bins=[-1, 19, 39, 64, 100],
        labels=["low", "medium", "high", "critical"],
    ).astype(str)

    # ------------------------------------------------------------------
    # 9. Human-readable factor strings
    # ------------------------------------------------------------------
    scores["risk_factors"] = _build_factors(clients, scores)

    return scores.sort_values("risk_score", ascending=False).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _build_factors(clients: pd.DataFrame, scores: pd.DataFrame) -> pd.Series:
    """Return a pipe-separated string of fired risk factors for each client.

    Example: "BNL Active | Chronic Homeless | Lost Contact >90d | Stalled Referral"
    Both DataFrames must share the same positional index (clients already reset).
    """
    # Each entry: (boolean mask Series aligned to clients.index, display label)
    factor_map: list[tuple[pd.Series, str]] = [
        (clients["bnl_active_flag"] == True,                             "BNL Active"),
        (clients["bnl_status"] == "active",                              "BNL Status Active"),
        (clients["chronic_homeless_flag"] == True,                       "Chronic Homeless"),
        (clients["ca_priority_level"] == "p3",                           "CA Priority P3"),
        (clients["ca_priority_level"] == "p2",                           "CA Priority P2"),
        (clients["assessment_acuity_level"].isin(["very_high", "high"]), "High Acuity"),
        (scores["days_since_contact"] > 90,                              "Lost Contact >90d"),
        (scores["days_since_contact"].between(31, 90),                   "No Contact 31-90d"),
        (scores["stalled_referral_count"] > 0,                           "Stalled Referral"),
        (scores["consent_expiry_days"].between(0, EXPIRY_WARNING_DAYS - 1), "Consent Expiring Soon"),
    ]

    # Build a boolean DataFrame, then join fired labels per row
    flag_df = pd.concat(
        [mask.rename(label).reset_index(drop=True) for mask, label in factor_map],
        axis=1,
    ).fillna(False)

    def _join_row(row: pd.Series) -> str:
        return " | ".join(col for col in row.index if row[col])

    return flag_df.apply(_join_row, axis=1)
