"""pytest suite for score_clients — proves gate-blocked clients are never scored,
and that every risk factor fires correctly with the right weight and label.

All tests use in-memory DataFrames; no file I/O, no Streamlit.
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.consent_gate import ConsentGate
from src.risk_scorer import (
    score_clients,
    STALLED_DAYS,
    EXPIRY_WARNING_DAYS,
    _WEIGHTS,
)

TODAY = date(2026, 4, 23)
TOMORROW = TODAY + timedelta(days=1)
FAR_FUTURE = str(TODAY + timedelta(days=90))   # outside 30-day expiry warning window


# ---------------------------------------------------------------------------
# Helpers for gate-integration tests (existing style)
# ---------------------------------------------------------------------------

def _make_client(client_id: str, consent_id: str) -> dict:
    return {
        "client_id": client_id,
        "current_consent_id": consent_id,
        "ocap_protected": False,
        "first_name": "Test",
        "last_name": "User",
        "bnl_active_flag": False,
        "bnl_status": "inactive",
        "chronic_homeless_flag": False,
        "ca_priority_level": "p1",
        "assessment_acuity_level": "low",
        "last_contact_date": str(TODAY),
    }


def _make_consent(consent_id: str, client_id: str, status: str) -> dict:
    return {
        "consent_id": consent_id,
        "client_id": client_id,
        "status": status,
        "expiry_date": FAR_FUTURE,
        "given_date": "2025-01-01",
        "sharing_scope_type": "network",
        "sharing_scope_agency_ids": "",
        "purpose_codes": "service_delivery",
        "legal_basis": "consent",
    }


# ---------------------------------------------------------------------------
# Helpers for isolated factor tests — zero-scoring baseline
# ---------------------------------------------------------------------------

def _sc_client(**overrides) -> dict:
    """Baseline client that scores exactly 0 (no flags, no risk factors)."""
    return {
        "client_id": "CLI-X",
        "current_consent_id": "CON-X",
        "ocap_protected": False,
        "first_name": "Test",
        "last_name": "User",
        "bnl_active_flag": False,
        "bnl_status": "inactive",
        "chronic_homeless_flag": False,
        "ca_priority_level": None,       # None → no CA points
        "assessment_acuity_level": "low",
        "last_contact_date": str(TODAY),  # 0 days → no contact penalty
        **overrides,
    }


def _sc_consent(expiry_date: str = FAR_FUTURE) -> pd.DataFrame:
    return pd.DataFrame([{
        "consent_id": "CON-X",
        "client_id": "CLI-X",
        "status": "active",
        "expiry_date": expiry_date,
        "given_date": "2025-01-01",
        "sharing_scope_type": "network",
        "sharing_scope_agency_ids": "",
        "purpose_codes": "service_delivery",
        "legal_basis": "consent",
    }])


def _empty_refs() -> pd.DataFrame:
    return pd.DataFrame({
        "client_id": pd.Series(dtype=str),
        "status": pd.Series(dtype=str),
        "submitted_at": pd.Series(dtype="datetime64[ns]"),
    })


def _score_one(client: dict, referrals=None, consent=None, **kwargs) -> pd.Series:
    """Score a single client dict and return the single result row."""
    return score_clients(
        pd.DataFrame([client]),
        _empty_refs() if referrals is None else referrals,
        _sc_consent() if consent is None else consent,
        reference_date=pd.Timestamp(TODAY),
        **kwargs,
    ).iloc[0]


# ---------------------------------------------------------------------------
# Gate integration — blocked clients never reach score_clients
# ---------------------------------------------------------------------------

class TestScoreClientsGateIntegration:
    def test_withdrawn_client_not_in_scored_output(self):
        """score_clients only receives gate-allowed clients; withdrawn must be absent."""
        clients = pd.DataFrame([
            _make_client("CLI-W", "CON-W"),
            _make_client("CLI-A", "CON-A"),
        ])
        consent = pd.DataFrame([
            _make_consent("CON-W", "CLI-W", "withdrawn"),
            _make_consent("CON-A", "CLI-A", "active"),
        ])
        referrals = _empty_refs()

        gate = ConsentGate(clients, consent, reference_date=TODAY)
        allowed, blocked = gate.filter_clients(clients)

        assert "CLI-W" in blocked["client_id"].values
        assert "CLI-W" not in allowed["client_id"].values

        scored = score_clients(allowed, referrals, consent)

        assert "CLI-W" not in scored["client_id"].values
        assert "CLI-A" in scored["client_id"].values

    def test_scored_output_has_risk_columns(self):
        """score_clients adds risk_score, risk_tier, risk_factors to allowed clients."""
        clients = pd.DataFrame([_make_client("CLI-A", "CON-A")])
        consent = pd.DataFrame([_make_consent("CON-A", "CLI-A", "active")])

        gate = ConsentGate(clients, consent, reference_date=TODAY)
        allowed, _ = gate.filter_clients(clients)
        scored = score_clients(allowed, _empty_refs(), consent)

        assert "risk_score" in scored.columns
        assert "risk_tier" in scored.columns
        assert "risk_factors" in scored.columns
        assert scored["risk_score"].iloc[0] >= 0
        assert scored["risk_tier"].iloc[0] in ("critical", "high", "medium", "low")


# ---------------------------------------------------------------------------
# Each of the 13 risk factors tested in isolation from the zero baseline
# ---------------------------------------------------------------------------

class TestRiskFactorScoring:
    def test_baseline_scores_zero(self):
        row = _score_one(_sc_client())
        assert row["risk_score"] == 0
        assert row["risk_factors"] == ""

    # --- BNL / homelessness ---

    def test_bnl_active_flag(self):
        row = _score_one(_sc_client(bnl_active_flag=True))
        assert row["risk_score"] == _WEIGHTS["bnl_active"]
        assert "BNL Active" in row["risk_factors"]

    def test_bnl_status_active(self):
        row = _score_one(_sc_client(bnl_status="active"))
        assert row["risk_score"] == _WEIGHTS["bnl_status_active"]
        assert "BNL Status Active" in row["risk_factors"]

    def test_chronic_homeless(self):
        row = _score_one(_sc_client(chronic_homeless_flag=True))
        assert row["risk_score"] == _WEIGHTS["chronic_homeless"]
        assert "Chronic Homeless" in row["risk_factors"]

    # --- CA priority ---

    def test_ca_priority_p3(self):
        row = _score_one(_sc_client(ca_priority_level="p3"))
        assert row["risk_score"] == _WEIGHTS["ca_p3"]
        assert "CA Priority P3" in row["risk_factors"]

    def test_ca_priority_p2(self):
        row = _score_one(_sc_client(ca_priority_level="p2"))
        assert row["risk_score"] == _WEIGHTS["ca_p2"]

    def test_ca_priority_p1(self):
        row = _score_one(_sc_client(ca_priority_level="p1"))
        assert row["risk_score"] == _WEIGHTS["ca_p1"]

    # --- Acuity ---

    def test_acuity_very_high(self):
        row = _score_one(_sc_client(assessment_acuity_level="very_high"))
        assert row["risk_score"] == _WEIGHTS["acuity_very_high"]
        assert "High Acuity" in row["risk_factors"]

    def test_acuity_high(self):
        row = _score_one(_sc_client(assessment_acuity_level="high"))
        assert row["risk_score"] == _WEIGHTS["acuity_high"]
        assert "High Acuity" in row["risk_factors"]

    def test_acuity_low_scores_zero(self):
        row = _score_one(_sc_client(assessment_acuity_level="low"))
        assert row["risk_score"] == 0

    # --- Lost contact ---

    def test_lost_contact_over_90_days(self):
        row = _score_one(_sc_client(last_contact_date=str(TODAY - timedelta(days=91))))
        assert row["risk_score"] == _WEIGHTS["lost_contact_90"]
        assert "Lost Contact >90d" in row["risk_factors"]

    def test_lost_contact_exactly_90_days_triggers_30_bucket(self):
        """90 days is <=90 so it falls in the >30 <=90 bucket, not >90."""
        row = _score_one(_sc_client(last_contact_date=str(TODAY - timedelta(days=90))))
        assert row["risk_score"] == _WEIGHTS["lost_contact_30"]
        assert "No Contact 31-90d" in row["risk_factors"]

    def test_lost_contact_31_to_90_days(self):
        row = _score_one(_sc_client(last_contact_date=str(TODAY - timedelta(days=45))))
        assert row["risk_score"] == _WEIGHTS["lost_contact_30"]
        assert "No Contact 31-90d" in row["risk_factors"]

    def test_lost_contact_30_days_does_not_trigger(self):
        """Exactly 30 days is <=30 so neither lost-contact bucket fires."""
        row = _score_one(_sc_client(last_contact_date=str(TODAY - timedelta(days=30))))
        assert row["risk_score"] == 0

    # --- Stalled referrals ---

    def test_stalled_referral_submitted_status(self):
        referrals = pd.DataFrame([{
            "client_id": "CLI-X", "status": "submitted",
            "submitted_at": pd.Timestamp(TODAY - timedelta(days=STALLED_DAYS + 1)),
        }])
        row = _score_one(_sc_client(), referrals=referrals)
        assert row["risk_score"] == _WEIGHTS["stalled_referral"]
        assert "Stalled Referral" in row["risk_factors"]

    def test_stalled_referral_pending_status(self):
        referrals = pd.DataFrame([{
            "client_id": "CLI-X", "status": "pending",
            "submitted_at": pd.Timestamp(TODAY - timedelta(days=20)),
        }])
        row = _score_one(_sc_client(), referrals=referrals)
        assert row["risk_score"] == _WEIGHTS["stalled_referral"]

    def test_recent_referral_not_stalled(self):
        """Referral submitted exactly STALLED_DAYS ago is NOT stalled (must be strictly greater)."""
        referrals = pd.DataFrame([{
            "client_id": "CLI-X", "status": "submitted",
            "submitted_at": pd.Timestamp(TODAY - timedelta(days=STALLED_DAYS)),
        }])
        row = _score_one(_sc_client(), referrals=referrals)
        assert row["risk_score"] == 0

    def test_closed_referral_never_stalled(self):
        """Closed referral does not count as stalled regardless of age."""
        referrals = pd.DataFrame([{
            "client_id": "CLI-X", "status": "closed",
            "submitted_at": pd.Timestamp(TODAY - timedelta(days=30)),
        }])
        row = _score_one(_sc_client(), referrals=referrals)
        assert row["risk_score"] == 0

    # --- Consent expiry ---

    def test_consent_expiring_within_warning_window(self):
        expiry = str(TODAY + timedelta(days=15))
        row = _score_one(_sc_client(), consent=_sc_consent(expiry_date=expiry))
        assert row["risk_score"] == _WEIGHTS["consent_expiring"]
        assert "Consent Expiring Soon" in row["risk_factors"]

    def test_consent_expiring_on_last_day_of_window(self):
        """Day EXPIRY_WARNING_DAYS-1 is inside [0, window-1] — should fire."""
        expiry = str(TODAY + timedelta(days=EXPIRY_WARNING_DAYS - 1))
        row = _score_one(_sc_client(), consent=_sc_consent(expiry_date=expiry))
        assert row["risk_score"] == _WEIGHTS["consent_expiring"]

    def test_consent_not_expiring_on_boundary_day(self):
        """Day EXPIRY_WARNING_DAYS (30) is outside [0, 29] — must NOT fire."""
        expiry = str(TODAY + timedelta(days=EXPIRY_WARNING_DAYS))
        row = _score_one(_sc_client(), consent=_sc_consent(expiry_date=expiry))
        assert row["risk_score"] == 0

    # --- Violation flag ---

    def test_has_violation_adds_score(self):
        row = _score_one(_sc_client(), violation_client_ids={"CLI-X"})
        assert row["risk_score"] == _WEIGHTS["has_violation"]

    def test_no_violation_for_other_client_id(self):
        row = _score_one(_sc_client(), violation_client_ids={"CLI-OTHER"})
        assert row["risk_score"] == 0


# ---------------------------------------------------------------------------
# Tier thresholds — exact boundary scores
# ---------------------------------------------------------------------------

class TestRiskTierThresholds:
    def test_score_65_is_critical(self):
        # bnl_active(25) + chronic_homeless(20) + ca_p2(10) + acuity_very_high(10) = 65
        row = _score_one(_sc_client(
            bnl_active_flag=True, chronic_homeless_flag=True,
            ca_priority_level="p2", assessment_acuity_level="very_high",
        ))
        assert row["risk_score"] == 65
        assert row["risk_tier"] == "critical"

    def test_score_40_is_high(self):
        # bnl_active(25) + ca_p3(15) = 40
        row = _score_one(_sc_client(bnl_active_flag=True, ca_priority_level="p3"))
        assert row["risk_score"] == 40
        assert row["risk_tier"] == "high"

    def test_score_20_is_medium(self):
        # bnl_status_active(10) + ca_p2(10) = 20
        row = _score_one(_sc_client(bnl_status="active", ca_priority_level="p2"))
        assert row["risk_score"] == 20
        assert row["risk_tier"] == "medium"

    def test_score_5_is_low(self):
        # ca_p1(5) = 5
        row = _score_one(_sc_client(ca_priority_level="p1"))
        assert row["risk_score"] == 5
        assert row["risk_tier"] == "low"


# ---------------------------------------------------------------------------
# Score cap at 100
# ---------------------------------------------------------------------------

class TestScoreCap:
    def test_score_capped_at_100(self):
        """Stacking enough factors to produce >100 raw score must clamp at 100."""
        # bnl_active(25)+bnl_status_active(10)+chronic_homeless(20)+ca_p3(15)
        # +acuity_very_high(10)+lost_contact_90(15)+consent_expiring(8) = 103 → 100
        expiry = str(TODAY + timedelta(days=15))
        row = _score_one(
            _sc_client(
                bnl_active_flag=True,
                bnl_status="active",
                chronic_homeless_flag=True,
                ca_priority_level="p3",
                assessment_acuity_level="very_high",
                last_contact_date=str(TODAY - timedelta(days=91)),
            ),
            consent=_sc_consent(expiry_date=expiry),
        )
        assert row["risk_score"] == 100
        assert row["risk_tier"] == "critical"
