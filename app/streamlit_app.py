"""Care Coordination Command Center — landing page.

Run from the project root:
    streamlit run app/streamlit_app.py

Set TRACK1_DATA_DIR to override the default data path:
    $env:TRACK1_DATA_DIR = "path/to/data/raw"
    streamlit run app/streamlit_app.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import streamlit as st

# Make src/ and the starter kit importable regardless of launch directory.
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
# Support two possible locations for the starter-kit: inside the project root
# or as a sibling in the parent folder. Insert both candidates on sys.path so
# pages run by Streamlit can always import `shared` regardless of layout.
_KIT_INSIDE = _PROJECT_ROOT / "buildersvault-hackathon-kit"
_KIT_PARENT = _PROJECT_ROOT.parent / "buildersvault-hackathon-kit"
_KIT_ROOT = _KIT_INSIDE if _KIT_INSIDE.exists() else _KIT_PARENT
for p in [str(_PROJECT_ROOT), str(_KIT_INSIDE), str(_KIT_PARENT)]:
    if p not in sys.path:
        sys.path.insert(0, p)

# Default data directory — override via environment variable.
DEFAULT_DATA_DIR = os.environ.get(
    "TRACK1_DATA_DIR",
    str(_KIT_ROOT / "tracks" / "referral-care-coordination" / "data" / "raw"),
)

st.set_page_config(
    page_title="Care Coordination Command Center",
    page_icon="🏥",
    layout="wide",
)

# Store data dir in session state so all pages share it.
if "data_dir" not in st.session_state:
    st.session_state["data_dir"] = DEFAULT_DATA_DIR

st.title("Care Coordination Command Center")
st.caption("Track 1 — Inter-Org Referral & Care Coordination | BuildersVault Social Services Hackathon")

st.markdown(
    """
    Referrals go silent between organizations. Consent expires unnoticed. Clients fall
    through the gaps. This dashboard gives frontline caseworkers a single view of every
    consent violation, at-risk client, and service history — with privacy enforcement as
    a first-class primitive, not an afterthought.

    **840 clients · 3,000 referrals · 10,000+ encounters · 9 Victoria-area organizations**
    """
)

st.divider()

col1, col2, col3 = st.columns(3)

with col1:
    st.markdown("### 🔴 Consent Monitor")
    st.markdown(
        "Live scan of all active consent violations — expired records, withdrawn consent "
        "still in use, OCAP overrides, and FOIPPA gaps."
    )
    st.page_link("pages/1_Consent_Monitor.py", label="Open Consent Monitor →")

with col2:
    st.markdown("### ⚠️ At-Risk Dashboard")
    st.markdown(
        "Clients most likely to fall through the gaps between organizations, ranked by risk score. "
        "Chronic homelessness, lost contact, stalled referrals, expiring consent."
    )
    st.page_link("pages/2_Risk_Dashboard.py", label="Open Risk Dashboard →")

with col3:
    st.markdown("### 👤 Client Timeline")
    st.markdown(
        "Full referral and encounter history for a single client, with consent status "
        "badges on every record. OCAP and withdrawn records shown as redaction notices."
    )
    st.page_link("pages/3_Client_Timeline.py", label="Open Client Timeline →")

st.success(
    "🔒 **Privacy gate active on all pages** — OCAP, PIPA, and FOIPPA rules are enforced "
    "before any client data is rendered. Blocked records are shown as redaction notices, "
    "not silently omitted."
)

st.divider()

with st.expander("Data directory (advanced)"):
    data_dir = st.text_input(
        "TRACK1_DATA_DIR",
        value=st.session_state["data_dir"],
        help="Path to the folder containing the Track 1 .parquet files.",
    )
    if data_dir != st.session_state["data_dir"]:
        st.session_state["data_dir"] = data_dir
        st.rerun()
    st.caption(f"Currently loaded from: `{st.session_state['data_dir']}`")
