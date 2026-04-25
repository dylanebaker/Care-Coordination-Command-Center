"""Consent Monitor — surfaces every active consent violation in the dataset.

This page runs the ConsentGate violation scanner and presents the results
as KPI cards, a breakdown chart, and a filterable drill-down table.
Every client record displayed here has already passed through the gate —
no withdrawn or OCAP-blocked data is exposed.
"""

from __future__ import annotations

import sys
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

# Make src/ and the starter kit importable. Support both possible starter-kit
# locations (inside project root, or as a sibling in the parent folder).
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_KIT_INSIDE = _PROJECT_ROOT / "buildersvault-hackathon-kit"
_KIT_PARENT = _PROJECT_ROOT.parent / "buildersvault-hackathon-kit"
_KIT_ROOT = _KIT_INSIDE if _KIT_INSIDE.exists() else _KIT_PARENT
for p in [str(_PROJECT_ROOT), str(_KIT_INSIDE), str(_KIT_PARENT)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from shared.src.loaders import load_track1  # noqa: E402
from src.consent_gate import ConsentGate, SEVERITY_CRITICAL, SEVERITY_WARNING  # noqa: E402


def _clean_type(raw: str) -> str:
    """Strip RED_FLAG_ prefix and replace underscores with spaces."""
    return raw.replace("RED_FLAG_", "").replace("_", " ").title()


# ---------------------------------------------------------------------------
# Data loading — cached so reruns don't re-scan 19k rows
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner="Scanning consent records…")
def _load(data_dir: str):
    tables = load_track1(data_dir)
    gate = ConsentGate(
        tables["clients"],
        tables["consent"],
        encounters_df=tables["encounters"],
        referrals_df=tables["referrals"],
        dsa_df=tables.get("dsa"),
    )
    violations = gate.get_violations()
    return tables, gate, violations


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
        page_title="Consent Monitor — Command Center",
        page_icon="🔴",
        layout="wide",
    )

    st.title("🔴 Consent Compliance Monitor")
    st.caption("Live scan of all active consent violations. Data passed through the privacy gate before display.")

    # Resolve data directory from session state (set by landing page) or default.
    data_dir = st.session_state.get(
        "data_dir",
        str(_KIT_ROOT / "tracks" / "referral-care-coordination" / "data" / "raw"),
    )

    try:
        tables, gate, violations = _load(data_dir)
    except FileNotFoundError as exc:
        st.error(str(exc))
        st.info("Run the Track 1 generator first:\n```\npython tracks/referral-care-coordination/generator/generate.py\n```")
        return

    _render_gate_sidebar(gate)

    if violations.empty:
        st.success("No consent violations detected.")
        return

    # -----------------------------------------------------------------------
    # 3c — KPI row
    # -----------------------------------------------------------------------
    n_critical = int((violations["severity"] == SEVERITY_CRITICAL).sum())
    n_warning  = int((violations["severity"] == SEVERITY_WARNING).sum())
    n_clients  = int(violations["client_id"][violations["client_id"] != ""].nunique())
    n_orgs     = int(violations["org_id"][violations["org_id"] != ""].nunique())

    st.markdown(
        f"**{len(violations)} active violations** across **{n_clients} clients** "
        f"at **{n_orgs} organizations**."
    )

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric(
            "Critical violations", n_critical,
            delta=f"{n_critical} need immediate action",
            delta_color="inverse",
            help="Violations that must be resolved before data can be used lawfully.",
        )
    with c2:
        st.metric(
            "Warnings", n_warning,
            delta=f"{n_warning} flagged for review",
            delta_color="off",
            help="Potential violations that need caseworker review.",
        )
    with c3:
        st.metric("Clients affected", n_clients, help="Unique clients with at least one violation.")
    with c4:
        st.metric("Orgs with violations", n_orgs, help="Organizations linked to at least one violation.")

    st.divider()

    # -----------------------------------------------------------------------
    # 3d — Violation breakdown bar chart
    # -----------------------------------------------------------------------
    st.subheader("Violation breakdown")
    st.caption(
        "Each bar is a distinct breach of PIPA, FOIPPA, or OCAP rules detected in the "
        "current dataset. Use the drill-down table below to inspect individual records."
    )

    counts = (
        violations["violation_type"]
        .value_counts()
        .reset_index()
    )
    counts.columns = ["Violation Type", "Count"]
    counts["Violation Type"] = counts["Violation Type"].apply(_clean_type)
    chart = (
        alt.Chart(counts)
        .mark_bar()
        .encode(
            x=alt.X("Violation Type:N", sort="-y",
                    axis=alt.Axis(labelAngle=0, labelOverlap=False, labelLimit=400)),
            y=alt.Y("Count:Q"),
            tooltip=["Violation Type", "Count"],
        )
        .properties(height=300)
    )
    st.altair_chart(chart, use_container_width=True)

    st.divider()

    # -----------------------------------------------------------------------
    # 3e — Drill-down table with filters
    # -----------------------------------------------------------------------
    st.subheader("Violation detail")

    all_types = sorted(violations["violation_type"].apply(_clean_type).unique().tolist())
    type_filter = st.multiselect(
        "Violation type",
        options=all_types,
        default=all_types,
    )

    filtered = violations[
        violations["violation_type"].apply(_clean_type).isin(type_filter)
    ].copy()

    # Friendlier display labels
    filtered["violation_type"] = filtered["violation_type"].apply(_clean_type)

    # Colour-code severity for readability
    def _severity_icon(s: str) -> str:
        return "🔴 critical" if s == SEVERITY_CRITICAL else "🟡 warning"

    filtered["severity"] = filtered["severity"].map(_severity_icon)

    display_cols = ["violation_type", "severity", "client_id", "org_id", "consent_id", "detail"]
    st.dataframe(
        filtered[display_cols].rename(columns={
            "violation_type": "Violation",
            "severity": "Severity",
            "client_id": "Client ID",
            "org_id": "Org ID",
            "consent_id": "Consent ID",
            "detail": "Detail",
        }),
        use_container_width=True,
        height=400,
    )
    st.caption(f"Showing {len(filtered)} of {len(violations)} violations.")

    st.divider()

    # -----------------------------------------------------------------------
    # 3f — Privacy gate status banner
    # -----------------------------------------------------------------------
    with st.expander("Privacy gate — active rules", expanded=True):
        st.markdown(
            """
| Rule | Status | Legal basis |
|---|---|---|
| Withdrawn consent | 🔴 Enforced — clients excluded from all views after withdrawal | PIPA s.23 |
| Expired consent | 🔴 Enforced — records locked until consent is renewed | PIPA s.23 |
| Single-agency scope | 🔴 Enforced — excluded from multi-org joins | PIPA sharing scope |
| OCAP-protected clients | 🔴 Enforced — restricted to approved partner orgs only | OCAP principles |
| FOIPPA missing purpose_codes | 🔴 Enforced — unlawful shares blocked at query time | FOIPPA s.33 |
            """
        )
        allowed, blocked = gate.filter_clients(gate._clients)
        st.metric("Clients visible after gate", len(allowed),
                  delta=f"{len(blocked)} blocked",
                  delta_color="inverse")


if __name__ == "__main__":
    main()
