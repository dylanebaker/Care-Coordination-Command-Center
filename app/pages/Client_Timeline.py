"""Client Timeline — full referral and encounter history for a single client.

Opened from the Risk Dashboard (session_state["selected_client_id"]) or directly.
Consent status is shown as a badge on every event.
Blocked records (withdrawn / expired consent) appear as explicit redaction
notices — they are never silently omitted.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

# Make src/ and the starter kit importable.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_KIT_ROOT = _PROJECT_ROOT.parent / "buildersvault-hackathon-kit"
for p in [str(_PROJECT_ROOT), str(_KIT_ROOT)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from shared.src.loaders import load_track1                           # noqa: E402
from src.consent_gate import (                                       # noqa: E402
    ConsentGate, BLOCK_WITHDRAWN, BLOCK_EXPIRED, BLOCK_OCAP, BLOCK_SINGLE_AGENCY,
    SEVERITY_CRITICAL,
)
from src.risk_scorer import score_clients                            # noqa: E402


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

CONSENT_BADGE = {
    "active":     "🟢 Active",
    "expired":    "🔴 Expired",
    "withdrawn":  "🔴 Withdrawn",
    "pending":    "🟡 Pending",
    "superseded": "⚫ Superseded",
}

STATUS_ICON = {
    # referral statuses
    "accepted":              "✅",
    "completed":             "✅",
    "pending":               "⏳",
    "submitted":             "📤",
    "declined":              "❌",
    "cancelled":             "🚫",
    # encounter outcome_flags
    "no_show":               "⚠️",
    "cancelled_by_client":   "🚫",
    "cancelled_by_provider": "🚫",
}


def _fmt_status(status: str) -> str:
    icon = STATUS_ICON.get(status, "•")
    return f"{icon} {status.replace('_', ' ').title()}" if status else "—"


def _fmt_badge(status: str) -> str:
    return CONSENT_BADGE.get(status, f"• {status}") if status else "—"


# ---------------------------------------------------------------------------
# Data loading — full tables cached once
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner="Loading data…")
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
    scored = scored.merge(
        tables["clients"][["client_id", "first_name", "last_name"]],
        on="client_id", how="left",
    )
    scored["display_name"] = (
        scored["first_name"].fillna("") + " " + scored["last_name"].fillna("")
    ).str.strip()
    return tables, gate, scored


# ---------------------------------------------------------------------------
# Timeline builder (5e)
# ---------------------------------------------------------------------------

def _build_timeline(
    client_id: str,
    referrals: pd.DataFrame,
    encounters: pd.DataFrame,
    consent: pd.DataFrame,
    client_consent_status: str,
    client_block_reason: str | None,
    sharing_scope_type: str = "all",
) -> pd.DataFrame:
    """Merge referrals + encounters for one client into a unified timeline."""

    # Consent lookup map: consent_record_id → status
    consent_status_map: dict[str, str] = (
        consent.set_index("consent_id")["status"].to_dict()
    )

    rows = []

    # --- Referral events ---
    client_refs = referrals[referrals["client_id"] == client_id].copy()
    for _, r in client_refs.iterrows():
        cstatus = consent_status_map.get(r.get("consent_record_id"), client_consent_status)
        is_blocked = cstatus in ("withdrawn", "expired")
        block_reason = (
            BLOCK_WITHDRAWN if cstatus == "withdrawn"
            else BLOCK_EXPIRED if cstatus == "expired"
            else None
        )
        # Fix 2: single-agency scope blocks cross-org referrals
        if (
            not is_blocked
            and sharing_scope_type == "single_agency_only"
            and str(r.get("referring_org_id") or "") != str(r.get("receiving_org_id") or "")
        ):
            is_blocked = True
            block_reason = BLOCK_SINGLE_AGENCY
        ref_detail = " / ".join(filter(None, [
            str(r.get("referral_type") or ""),
            str(r.get("referral_reason") or ""),
            str(r.get("referral_priority") or ""),
        ]))
        rows.append({
            "event_date":        r.get("submitted_at"),
            "event_type":        "📋 Referral",
            "event_id":          r.get("referral_id"),
            "org":               f"{r.get('referring_org_id', '')} → {r.get('receiving_org_id', '')}",
            "status":            _fmt_status(str(r.get("status") or "")),
            "detail":            ref_detail,
            "consent_status":    cstatus,
            "consent_record_id": r.get("consent_record_id"),
            "is_blocked":        is_blocked,
            "block_reason":      block_reason,
        })

    # --- Encounter events ---
    client_encs = encounters[encounters["client_id"] == client_id].copy()
    for _, e in client_encs.iterrows():
        is_blocked = client_consent_status in ("withdrawn", "expired")
        enc_detail = " / ".join(filter(None, [
            str(e.get("encounter_type") or ""),
            str(e.get("reason_for_service") or ""),
        ]))
        rows.append({
            "event_date":        e.get("encounter_start"),
            "event_type":        "🤝 Encounter",
            "event_id":          e.get("encounter_id"),
            "org":               str(e.get("org_id") or ""),
            "status":            _fmt_status(str(e.get("outcome_flag") or "")),
            "detail":            enc_detail,
            "consent_status":    client_consent_status,
            "consent_record_id": None,
            "is_blocked":        is_blocked,
            "block_reason":      client_block_reason,
        })

    if not rows:
        return pd.DataFrame()

    timeline = pd.DataFrame(rows)
    timeline["event_date"] = pd.to_datetime(timeline["event_date"], errors="coerce")
    timeline = timeline.sort_values("event_date", ascending=False).reset_index(drop=True)
    return timeline


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
        page_title="Client Timeline — Command Center",
        page_icon="👤",
        layout="wide",
    )

    st.title("👤 Client Timeline")
    st.caption("Full referral and encounter history. Blocked records appear as redaction notices.")

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
    # 5h — Client selector (pre-filled from session state)
    # -----------------------------------------------------------------------
    allowed_ids = scored["client_id"].tolist()
    name_map = dict(zip(scored["client_id"], scored["display_name"]))

    default_id = st.session_state.get("selected_client_id")
    default_idx = allowed_ids.index(default_id) if default_id in allowed_ids else 0

    selected_id = st.selectbox(
        "Select client",
        options=allowed_ids,
        index=default_idx,
        format_func=lambda cid: f"{name_map.get(cid, cid)} ({cid})",
    )
    st.caption(
        f"Showing {len(allowed_ids)} gate-allowed clients. "
        "Blocked clients are not accessible from this view."
    )
    st.session_state["selected_client_id"] = selected_id

    # -----------------------------------------------------------------------
    # 5c — Client profile header
    # -----------------------------------------------------------------------
    client_row = tables["clients"][tables["clients"]["client_id"] == selected_id]
    if client_row.empty:
        st.error(f"Client {selected_id} not found.")
        return
    c = client_row.iloc[0]

    # Resolve current consent record.
    # Primary: use clients.current_consent_id FK.
    # Fallback: scan all consent records for this client; pick most severe status.
    _STATUS_SEVERITY = {"withdrawn": 4, "expired": 3, "pending": 2, "active": 1, "superseded": 0}

    consent_row = None
    if pd.notna(c.get("current_consent_id")):
        cr = tables["consent"][tables["consent"]["consent_id"] == c["current_consent_id"]]
        if not cr.empty:
            consent_row = cr.iloc[0]

    if consent_row is None:
        # Fallback: all consent records for this client, worst status wins
        all_cr = tables["consent"][tables["consent"]["client_id"] == selected_id]
        if not all_cr.empty:
            all_cr = all_cr.copy()
            all_cr["_sev"] = all_cr["status"].map(_STATUS_SEVERITY).fillna(0)
            consent_row = all_cr.sort_values("_sev", ascending=False).iloc[0]

    client_consent_status = str(consent_row["status"]) if consent_row is not None else "unknown"
    client_block_reason = (
        BLOCK_WITHDRAWN if client_consent_status == "withdrawn"
        else BLOCK_EXPIRED if client_consent_status == "expired"
        else None
    )
    client_sharing_scope = str(
        consent_row.get("sharing_scope_type") if consent_row is not None else "all"
    ) or "all"

    # Fix 1: OCAP hard-block — if OCAP-protected and no approved partners listed,
    # deny access entirely (problem-framing.md Privacy constraints §1).
    if c.get("ocap_protected"):
        approved_raw = str(consent_row.get("sharing_scope_agency_ids") or "") if consent_row is not None else ""
        approved = {s.strip() for s in approved_raw.split(";") if s.strip()}
        if not approved:
            st.error(
                f"⛔ **ACCESS DENIED — OCAP-Protected Client**\n\n"
                f"This client is governed by "
                f"**{c.get('ocap_governing_nation') or 'an Indigenous governing body'}** "
                f"under OCAP principles. No approved partner organizations are listed on "
                f"their consent record. Access from this view is not permitted.\n\n"
                f"_Rule: OCAP-protected client data cannot be shared beyond the governing "
                f"nation's agreed scope (problem-framing.md, Privacy constraints §1)._"
            )
            return
        else:
            st.warning(
                f"⚠️ **OCAP-Protected Client** — governed by "
                f"**{c.get('ocap_governing_nation') or 'an Indigenous governing body'}**. "
                "Data use is restricted per OCAP principles. Only approved partner "
                "organizations may access records beyond this profile summary."
            )

    # Consent status banner
    badge = _fmt_badge(client_consent_status)
    if client_consent_status in ("expired", "withdrawn"):
        st.error(
            f"Consent status: **{badge}** — some records below are gate-blocked "
            "and shown as redaction notices."
        )
    else:
        st.info(f"Consent status: **{badge}**")

    # Profile columns
    p1, p2, p3 = st.columns([2, 2, 3])
    with p1:
        st.markdown(f"### {c.get('first_name', '')} {c.get('last_name', '')}")
        st.markdown(f"**ID:** `{selected_id}`  |  **Age:** {c.get('age', '—')}  |  **Gender:** {c.get('gender', '—')}")
        st.markdown(f"**Housing:** {c.get('housing_status', '—')}")
        st.markdown(f"**Sleeping:** {c.get('current_sleeping_location', '—')}")
    with p2:
        st.markdown("**Flags:**")
        flags = []
        if c.get("chronic_homeless_flag"):  flags.append("🏠 Chronic Homeless")
        if c.get("bnl_active_flag"):         flags.append("📋 BNL Active")
        if c.get("bnl_status") == "active":  flags.append(f"📊 BNL: {c.get('bnl_status')}")
        if c.get("ca_priority_level"):       flags.append(f"⭐ CA Priority: {c.get('ca_priority_level').upper()}")
        if c.get("veteran_status"):          flags.append("🎖️ Veteran")
        if c.get("mental_health_flag"):      flags.append("🧠 Mental Health")
        if c.get("substance_use_flag"):      flags.append("💊 Substance Use")
        if c.get("ocap_protected"):          flags.append("🛡️ OCAP Protected")
        for f in flags:
            st.markdown(f"- {f}")
        if not flags:
            st.markdown("_None_")
    with p3:
        # 5d — Consent details expander
        with st.expander("Consent details"):
            if consent_row is not None:
                st.markdown(f"**Type:** {consent_row.get('consent_type', '—')}")
                st.markdown(f"**Legal basis:** {consent_row.get('legal_basis', '—')}")
                st.markdown(f"**Purpose codes:** {consent_row.get('purpose_codes', '—')}")
                st.markdown(f"**Scope:** {consent_row.get('sharing_scope_type', '—')}")
                agencies = consent_row.get('sharing_scope_agency_ids')
                if agencies:
                    st.markdown(f"**Approved agencies:** {agencies}")
                st.markdown(f"**Effective:** {consent_row.get('effective_date', '—')}")
                st.markdown(f"**Expires:** {consent_row.get('expiry_date', '—') or '_ongoing_'}")
                if consent_row.get("withdrawal_date"):
                    st.markdown(f"**Withdrawn:** {consent_row.get('withdrawal_date')}")
            else:
                st.markdown("_No consent record linked to this client._")

    st.divider()

    # -----------------------------------------------------------------------
    # 5e+5f — Build and render the timeline
    # -----------------------------------------------------------------------
    timeline = _build_timeline(
        selected_id,
        tables["referrals"],
        tables["encounters"],
        tables["consent"],
        client_consent_status,
        client_block_reason,
        sharing_scope_type=client_sharing_scope,
    )

    if timeline.empty:
        st.info("No referrals or encounters found for this client.")
        return

    n_blocked = int(timeline["is_blocked"].sum())
    n_total   = len(timeline)
    st.subheader(f"Timeline — {n_total} events ({n_blocked} gate-blocked)")
    if n_blocked == n_total:
        st.error(
            f"⛔ All {n_total} records for this client are gate-blocked. "
            "No timeline data is accessible under current consent rules."
        )
        return
    if n_blocked:
        st.caption(f"🚫 {n_blocked} records are blocked by the consent gate and shown as redaction notices.")

    # Build display DataFrame
    display = timeline.copy()
    display["Date"] = display["event_date"].dt.strftime("%b %d %Y  %H:%M").fillna("—")
    display["Consent"] = display["consent_status"].apply(_fmt_badge)

    # Blocked rows: replace detail with redaction notice
    blocked_mask = display["is_blocked"]
    display.loc[blocked_mask, "detail"] = (
        "⛔ " + display.loc[blocked_mask, "block_reason"].fillna("Access blocked")
    )
    display.loc[blocked_mask, "Consent"] = "🚫 Blocked"

    table_df = display[["Date", "event_type", "org", "status", "detail", "Consent"]].rename(columns={
        "event_type": "Type",
        "org":        "Org",
        "status":     "Status",
        "detail":     "Detail",
    })

    st.dataframe(table_df, use_container_width=True, height=450)

    st.divider()

    # -----------------------------------------------------------------------
    # 5g — Event detail expander
    # -----------------------------------------------------------------------
    st.subheader("Inspect event")

    event_options = timeline["event_id"].tolist()
    event_labels = {
        row["event_id"]: (
            f"{row['event_date'].strftime('%b %d %Y') if pd.notna(row['event_date']) else '?'}"
            f" — {row['event_type']} — {row['event_id']}"
        )
        for _, row in timeline.iterrows()
    }

    selected_event = st.selectbox(
        "Select event to inspect",
        options=event_options,
        format_func=lambda eid: event_labels.get(eid, eid),
    )

    if selected_event:
        event_row = timeline[timeline["event_id"] == selected_event].iloc[0]
        if event_row["is_blocked"]:
            st.error(f"⛔ Access blocked: **{event_row['block_reason']}**")
            st.caption("This record is not viewable because the client's consent does not permit it.")
        else:
            with st.expander("Full event detail", expanded=True):
                detail_data = {
                    "Event ID":       event_row["event_id"],
                    "Type":           event_row["event_type"],
                    "Date":           str(event_row["event_date"]),
                    "Org":            event_row["org"],
                    "Status":         event_row["status"],
                    "Detail":         event_row["detail"],
                    "Consent record": str(event_row.get("consent_record_id") or "—"),
                    "Consent status": event_row["consent_status"],
                }
                for k, v in detail_data.items():
                    st.markdown(f"**{k}:** {v}")


if __name__ == "__main__":
    main()
