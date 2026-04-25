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
│       ├── 1_Consent_Monitor.py    # Violation scan dashboard
│       ├── 2_Risk_Dashboard.py     # Risk-ranked client list
│       └── 3_Client_Timeline.py    # Per-client consent-badged timeline
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

Follow these steps in order. Important: install dependencies before running the data generator — the generator (and the app) require packages such as `numpy`, `pandas`, and `Faker`.

### Prerequisites

- Python 3.10+
- Git (to clone with submodules)

### 1) Clone (with submodules)

Clone the repo including the BuildersVault starter kit submodule (recommended):

```bash
git clone --recurse-submodules https://github.com/dylanebaker/Care-Coordination-Command-Center.git
```

If you already cloned without submodules:

```bash
git submodule update --init --recursive
```

To update just the starter kit later:

```bash
git -C buildersvault-hackathon-kit pull origin main
```

### 2) Create and activate a virtual environment (recommended)

```bash
cd "Care Coordination Command Center"

# Windows (PowerShell)
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# macOS / Linux
python -m venv .venv
source .venv/bin/activate
```

### 3) Install dependencies (do this before generating data)

Install the app requirements and the starter-kit requirements so both the dashboard and the data generator have the packages they need (this ensures `numpy` is available when you run the generator):

```bash
pip install -r requirements.txt
pip install -r buildersvault-hackathon-kit/requirements.txt
```

If you prefer a smaller install for only generation, install the kit requirements instead:

```bash
pip install -r buildersvault-hackathon-kit/requirements.txt
```

### 4) Generate the Track 1 data (optional)

If you need synthetic Track 1 files, run the generator from the starter kit. With the virtual environment active and the kit requirements installed, this should run without missing-module errors:

```bash
cd buildersvault-hackathon-kit
python tracks/referral-care-coordination/generator/generate.py
```

If you see an error like `ModuleNotFoundError: No module named 'numpy'`, return to step 3 and run the `pip install -r buildersvault-hackathon-kit/requirements.txt` command, or run `pip install numpy`.

### 5) Point the app at the generated data

PowerShell example:

```powershell
$env:TRACK1_DATA_DIR = "D:\\path\\to\\repo\\buildersvault-hackathon-kit\\tracks\\referral-care-coordination\\data\\raw"
streamlit run app/streamlit_app.py
```

bash / macOS example:

```bash
export TRACK1_DATA_DIR="$(pwd)/buildersvault-hackathon-kit/tracks/referral-care-coordination/data/raw"
streamlit run app/streamlit_app.py
```

### 6) Launch the app

From the project root (with the venv active):

```bash
streamlit run app/streamlit_app.py
```

The app opens at http://localhost:8501

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
