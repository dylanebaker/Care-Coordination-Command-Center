# Privacy-First Care Coordination Command Center

> **BuildersVault Social Services Hackathon — Track 1: Inter-Org Referral & Care Coordination**
> Demo night: Saturday April 25, 2026 · University of Victoria

---

## What it does

Referrals go silent between organizations. Consent expires unnoticed. Clients fall
through the gaps. This dashboard gives frontline caseworkers a single view of every
consent violation, at-risk client, and service history — with privacy enforcement as
a first-class primitive, not an afterthought.

Three pages, one consent gate:

| Page | What it shows |
|---|---|
| **Consent Monitor** | Live scan of all active consent violations — expired records, withdrawn consent, OCAP overrides, and FOIPPA gaps |
| **At-Risk Dashboard** | Clients most likely to fall through inter-org gaps, ranked by a 13-factor rule-based risk score |
| **Client Timeline** | Full referral and encounter history for a single client, with consent badges on every record and OCAP/withdrawn events shown as redaction notices |

Dataset: **840 clients · 3,000 referrals · 10,000+ encounters · 9 Victoria-area organizations** (synthetic, generated from BuildersVault starter kit).

---

## Track declaration

**Track 1 — Inter-Org Referral & Care Coordination**

---

## The privacy gate — rules enforced and where

Every data access path passes through `src/consent_gate.py` before any client data is
rendered. Five hard rules are enforced:

| Rule | Where enforced | Legal basis |
|---|---|---|
| Withdrawn consent | `consent_gate.py → filter_clients()` | PIPA s.23 |
| Expired consent | `consent_gate.py → filter_clients()` | PIPA s.23 |
| Single-agency scope | `consent_gate.py → filter_clients(multi_org_view=True)` | PIPA sharing scope |
| OCAP-protected clients | `consent_gate.py → _compute_ocap_blocked_ids()` | OCAP principles |
| FOIPPA missing `purpose_codes` | `consent_gate.py → filter_referrals()` | FOIPPA s.33 |

The sidebar on every page shows a live gate-status widget (clients visible / blocked) so
caseworkers always know the enforcement state.

---

## Architecture

```
Care Coordination Command Center/
├── app/
│   ├── streamlit_app.py          # Landing page — navigation hub
│   └── pages/
│       ├── Consent_Monitor.py    # Violation scan dashboard
│       ├── Risk_Dashboard.py     # Risk-ranked client list
│       └── Client_Timeline.py    # Per-client consent-badged timeline
├── src/
│   ├── consent_gate.py           # Privacy gate — all 5 rules live here
│   └── risk_scorer.py            # 13-factor rule-based risk scoring
├── tests/
│   ├── test_consent_gate.py      # 29 unit tests for the gate
│   └── test_risk_scorer.py       # 30 unit tests for the scorer
└── requirements.txt
```

**`consent_gate.py`** — `ConsentGate` takes the full clients + consent tables at
construction time and pre-computes blocked IDs for each rule. `filter_clients()` and
`filter_referrals()` return a named tuple `(allowed, blocked)` and never mutate input
data. `get_violations()` returns a tidy DataFrame of all active violations.

**`risk_scorer.py`** — `score_clients()` applies 13 independent weighted factors
(chronic homelessness, BNL status, acuity, lost contact, stalled referrals, expiring
consent, active violations) to produce a score capped at 100, then classifies each
client into a tier: critical (≥65), high (≥40), medium (≥20), low (<20).

---

## How to run it

### Using the BuildersVault starter kit (recommended)

This repository includes the BuildersVault starter kit as a git submodule at `buildersvault-hackathon-kit`. The submodule contains the data generator and the synthetic Track 1 dataset. We keep generated binary data out of this repo — do not copy or commit `.parquet` files or the generated `track1.sqlite` into this repository (they are excluded by `.gitignore`).

Clone with submodules:
```bash
git clone --recurse-submodules https://github.com/YOUR_GH_USERNAME/YOUR_REPO_NAME.git
```

If you've already cloned without submodules:
```bash
git submodule update --init --recursive
```

To update the starter kit later:
```bash
git -C buildersvault-hackathon-kit pull origin main
```

Generate Track 1 data from the kit (run inside your venv):
```bash
cd buildersvault-hackathon-kit
python -m pip install Faker==25.0.0
python tracks/referral-care-coordination/generator/generate.py
```

Point the app at the generated files (PowerShell example):
```powershell
$env:TRACK1_DATA_DIR = "D:\\path\\to\\repo\\buildersvault-hackathon-kit\\tracks\\referral-care-coordination\\data\\raw"
```

Or in bash/macOS:
```bash
export TRACK1_DATA_DIR="$(pwd)/buildersvault-hackathon-kit/tracks/referral-care-coordination/data/raw"
```

### Prerequisites

- Python 3.10+
- The Track 1 data files in `buildersvault-hackathon-kit/tracks/referral-care-coordination/data/raw/`

### 1. Generate the Track 1 data (if not already done)

```bash
cd buildersvault-hackathon-kit
python tracks/referral-care-coordination/generator/generate.py
```

### 2. Create and activate a virtual environment

```bash
cd "Care Coordination Command Center"

# Windows (PowerShell)
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# macOS / Linux
python -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Launch

```bash
streamlit run app/streamlit_app.py
```

The app opens at **http://localhost:8501**.

To point the app at a different data folder:

```bash
# Windows (PowerShell)
$env:TRACK1_DATA_DIR = "C:\path\to\data\raw"
streamlit run app/streamlit_app.py

# macOS / Linux
TRACK1_DATA_DIR=/path/to/data/raw streamlit run app/streamlit_app.py
```

---

## Running the tests

```bash
pytest tests/ -v
```

Expected output: **59 passed** in under 2 seconds.

The test suite covers:
- All 5 consent gate rules (withdrawn, expired, OCAP, single-agency, FOIPPA)
- Edge cases: null `current_consent_id`, overlapping blocks, referral inheritance
- Risk scorer: all 13 factors individually, tier thresholds, score cap, gate integration

---

## Privacy statement

Every data access path in this application passes through a `ConsentGate` before
rendering. The gate enforces five hard rules derived from BC's PIPA, FOIPPA, and OCAP
principles: (1) clients with withdrawn consent are excluded from all views; (2) clients
with expired consent are locked and surfaced as violations; (3) clients with
single-agency scope are excluded from any multi-org join; (4) OCAP-protected clients are
restricted to their approved partner organizations only; (5) FOIPPA records missing
`purpose_codes` are refused at the referral layer. These rules are unit-tested with
59 automated assertions (`pytest`) and are always visible to the caseworker through the
sidebar gate-status widget on every page.

---

## Attribution

Data: BuildersVault Social Services Hackathon starter kit (synthetic), CC BY 4.0.
Problem framing by Lautaro Cepeda.
