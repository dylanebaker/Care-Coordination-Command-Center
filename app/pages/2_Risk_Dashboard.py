"""At-Risk Client Dashboard — ranked list of clients most likely to fall through the gaps.

Clients are scored by a rule-based risk model (src/risk_scorer.py) and filtered
through the consent gate before any data is displayed.
Selecting a client sets session state so the Client Timeline page can open that record.
"""

from __future__ import annotations

import sys
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

# Make src/ and the starter kit importable.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_KIT_ROOT = _PROJECT_ROOT.parent / "buildersvault-hackathon-kit"
_KIT_INSIDE = _PROJECT_ROOT / "buildersvault-hackathon-kit"
_KIT_PARENT = _PROJECT_ROOT.parent / "buildersvault-hackathon-kit"
_KIT_ROOT = _KIT_INSIDE if _KIT_INSIDE.exists() else _KIT_PARENT
for p in [str(_PROJECT_ROOT), str(_KIT_INSIDE), str(_KIT_PARENT)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from shared.src.loaders import load_track1       # noqa: E402
from src.consent_gate import ConsentGate         # noqa: E402
from src.risk_scorer import score_clients        # noqa: E402


# ---------------------------------------------------------------------------
# Tier display helpers
# ---------------------------------------------------------------------------

_TIER_ICON = {
    "critical": "🔴",
    "high":     "🟠",
    "medium":   "🟡",
    "low":      "🟢",
}

_TIER_ORDER = ["critical", "high", "medium", "low"]


# ---------------------------------------------------------------------------
# Data loading — cached
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner="Scoring clients…")
def _load(data_dir: str):
    tables = load_track1(data_dir)
    gate = ConsentGate(
        tables["clients"], tables["consent"],
        encounters_df=tables["encounters"],
        referrals_df=tables["referrals"],
        dsa_df=tables.get("dsa"),
    )
    violations = gate.get_violations()
    violation_ids = set(violations["client_id"].dropna())
    allowed, _ = gate.filter_clients(tables["clients"])
    scored = score_clients(
        allowed, tables["referrals"], tables["consent"],
        violation_client_ids=violation_ids,
    )
    # Attach display name for convenience
    scored = scored.merge(
        tables["clients"][["client_id", "first_name", "last_name"]],
        on="client_id", how="left",
    )
    scored["name"] = scored["first_name"].fillna("") + " " + scored["last_name"].fillna("")
    scored["name"] = scored["name"].str.strip()
    return tables, gate, scored


# ---------------------------------------------------------------------------
# Sidebar gate-status widget — shown on every page
# ---------------------------------------------------------------------------

def _render_gate_sidebar(gate: ConsentGate) -> None:
    with st.sidebar:
        st.markdown("### 🔒 Privacy Gate Active")
        st.markdown(
            "All data passes through the consent gate before display.  \n"
            "The following rules are enforced:"
        )
        st.markdown(
            "- 🔴 Withdrawn consent — excluded  \n"
            "- 🔴 Expired consent — locked  \n"
            "- 🔴 Single-agency scope — multi-org blocked  \n"
            "- 🔴 OCAP protection — partner-only access  \n"
            "- 🔴 FOIPPA purpose codes — required  \n"
        )
        allowed, blocked = gate.filter_clients(gate._clients)
        st.metric(
            "Clients visible", len(allowed),
            delta=f"{len(blocked)} blocked",
            delta_color="inverse",
        )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    st.set_page_config(
        page_title="At-Risk Dashboard — Command Center",
        page_icon="⚠️",
        layout="wide",
    )

    st.title("⚠️ At-Risk Client Dashboard")
    st.caption("Clients ranked by rule-based risk score. Gate-blocked clients are excluded entirely.")

    data_dir = st.session_state.get(
        "data_dir",
        str(_KIT_ROOT / "tracks" / "referral-care-coordination" / "data" / "raw"),
    )

    try:
        tables, gate, scored = _load(data_dir)
    except FileNotFoundError as exc:
        st.error(str(exc))
        return

    _render_gate_sidebar(gate)

    # -----------------------------------------------------------------------
    # KPI row — one metric per tier
    # -----------------------------------------------------------------------
    tier_counts = scored["risk_tier"].value_counts()
    n_critical = int(tier_counts.get("critical", 0))
    n_high     = int(tier_counts.get("high",     0))
    n_medium   = int(tier_counts.get("medium",   0))
    n_low      = int(tier_counts.get("low",      0))

    st.markdown(
        f"**{len(scored)} clients scored** — "
        f"{n_critical} critical, {n_high} high, {n_medium} medium, {n_low} low."
    )

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("🔴 Critical", n_critical,
                  delta=f"{n_critical} need immediate follow-up",
                  delta_color="inverse")
    with c2:
        st.metric("🟠 High", n_high,
                  delta=f"{n_high} flagged",
                  delta_color="off")
    with c3:
        st.metric("🟡 Medium", n_medium)
    with c4:
        st.metric("🟢 Low", n_low)

    st.divider()

    # -----------------------------------------------------------------------
    # Factor frequency bar chart
    # -----------------------------------------------------------------------
    st.subheader("Risk factor frequency")
    st.caption("How many clients triggered each factor.")

    factor_series = (
        scored["risk_factors"]
        .dropna()
        .loc[lambda s: s != ""]   # skip clients with no factors
        .str.split(" | ", regex=False)
        .explode()
        .str.strip()
        .loc[lambda s: s != ""]   # drop any empty tokens produced by split
    )
    factor_counts = (
        factor_series
        .value_counts()
        .reset_index()
    )
    factor_counts.columns = ["Factor", "Clients"]
    chart = (
        alt.Chart(factor_counts)
        .mark_bar()
        .encode(
            x=alt.X("Factor:N", sort="-y",
                    axis=alt.Axis(labelAngle=0, labelOverlap=False, labelLimit=400)),
            y=alt.Y("Clients:Q"),
            tooltip=["Factor", "Clients"],
        )
        .properties(height=280)
    )
    st.altair_chart(chart, use_container_width=True)

    st.divider()

    # -----------------------------------------------------------------------
    # How scores work
    # -----------------------------------------------------------------------
    with st.expander("📊 How scores work"):
        st.markdown(
            """
| Factor | Points | Condition |
|---|---|---|
| On the By-Name List (BNL) | +25 | `bnl_active_flag = True` |
| BNL status active | +10 | `bnl_status = 'active'` |
| Chronic homelessness | +20 | `chronic_homeless_flag = True` |
| CA priority: P3 | +15 | `ca_priority_level = 'p3'` |
| CA priority: P2 | +10 | `ca_priority_level = 'p2'` |
| CA priority: P1 | +5 | `ca_priority_level = 'p1'` |
| Acuity: very high | +10 | `acuity_level = 'very_high'` |
| Acuity: high | +7 | `acuity_level = 'high'` |
| Lost contact >90 days | +15 | days since last encounter > 90 |
| Lost contact 30–90 days | +8 | days since last encounter 30–90 |
| Stalled referral | +10 | at least one referral stalled > 14 days |
| Consent expiring <30 days | +8 | expiry within 30 days |
| Active consent violation | +5 | flagged by the consent gate |

Scores are capped at **100**. Tiers: critical ≥65, high ≥40, medium ≥20, low <20.
            """
        )

    # -----------------------------------------------------------------------
    # Filters + ranked table
    # -----------------------------------------------------------------------
    st.subheader("Ranked clients")
    st.caption(
        "Ranked by composite score from 13 independent rule-based factors. "
        "Gate-blocked clients are excluded entirely."
    )

    col_f1, col_f2 = st.columns([1, 3])
    with col_f1:
        tier_filter = st.multiselect(
            "Tier",
            options=_TIER_ORDER,
            default=["critical", "high"],
            format_func=lambda t: f"{_TIER_ICON[t]} {t.title()}",
        )
    with col_f2:
        all_factors = sorted(factor_series.unique().tolist())
        factor_filter = st.multiselect(
            "Must include factor (leave blank = show all)",
            options=all_factors,
            default=[],
        )

    display = scored[scored["risk_tier"].isin(tier_filter)].copy()
    if factor_filter:
        mask = display["risk_factors"].apply(
            lambda f: any(fac in (f or "") for fac in factor_filter)
        )
        display = display[mask]

    # Build display DataFrame
    table_df = display[
        ["risk_tier", "risk_score", "name", "client_id",
         "risk_factors", "days_since_contact",
         "stalled_referral_count", "consent_expiry_days"]
    ].copy()
    table_df["risk_tier"] = table_df["risk_tier"].map(
        lambda t: f"{_TIER_ICON.get(t, '')} {t}"
    )
    table_df = table_df.rename(columns={
        "risk_tier":             "Tier",
        "risk_score":            "Score",
        "name":                  "Name",
        "client_id":             "Client ID",
        "risk_factors":          "Risk Factors",
        "days_since_contact":    "Days Since Contact",
        "stalled_referral_count":"Stalled Referrals",
        "consent_expiry_days":   "Consent Expires In (days)",
    })

    st.dataframe(table_df, use_container_width=True, height=420)
    st.caption(f"Showing {len(display)} of {len(scored)} scored clients.")

    st.divider()

    # -----------------------------------------------------------------------
    # Client selection → session state for Client Timeline
    # -----------------------------------------------------------------------
    st.subheader("Open client timeline")

    if display.empty:
        st.info("No clients match the current filters.")
        return

    options = {
        row["client_id"]: f"{row['name']} — score {row['risk_score']} ({row['risk_tier']})"
        for _, row in display.head(200).iterrows()
    }

    selected_id = st.selectbox(
        "Select a client",
        options=list(options.keys()),
        format_func=lambda cid: options[cid],
    )

    if selected_id:
        st.session_state["selected_client_id"] = selected_id
        st.success(f"Selected: **{options[selected_id]}**")
        st.page_link("pages/3_Client_Timeline.py", label="Open Client Timeline →")


if __name__ == "__main__":
    main()
