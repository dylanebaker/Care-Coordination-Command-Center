"""pytest suite for ConsentGate — proves every privacy rule rejects bad inputs.

All tests use in-memory DataFrames; no file I/O, no Streamlit, no load_track1.
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import pytest

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.consent_gate import (
    ConsentGate,
    BLOCK_WITHDRAWN,
    BLOCK_EXPIRED,
    BLOCK_SINGLE_AGENCY,
    BLOCK_OCAP,
    BLOCK_FOIPPA_NO_PURPOSE,
)

# ---------------------------------------------------------------------------
# Shared helpers — minimal DataFrame factories
# ---------------------------------------------------------------------------

TODAY = date(2026, 4, 23)
YESTERDAY = TODAY - timedelta(days=1)
TOMORROW = TODAY + timedelta(days=1)


def _clients(*rows: dict) -> pd.DataFrame:
    """Build a minimal clients DataFrame from keyword-argument dicts."""
    defaults = {
        "client_id": "CLI-X",
        "ocap_protected": False,
        "current_consent_id": None,
        "first_name": "Test",
        "last_name": "User",
    }
    return pd.DataFrame([{**defaults, **r} for r in rows])


def _consent(*rows: dict) -> pd.DataFrame:
    """Build a minimal consent_records DataFrame from keyword-argument dicts."""
    defaults = {
        "consent_id": "CON-X",
        "client_id": "CLI-X",
        "status": "active",
        "expiry_date": str(TOMORROW),
        "given_date": "2025-01-01",
        "sharing_scope_type": "network",
        "sharing_scope_agency_ids": "",
        "purpose_codes": "service_delivery",
        "legal_basis": "consent",
    }
    return pd.DataFrame([{**defaults, **r} for r in rows])


def _gate(clients_df, consent_df, **kwargs) -> ConsentGate:
    return ConsentGate(clients_df, consent_df, reference_date=TODAY, **kwargs)


# ---------------------------------------------------------------------------
# 7b — Withdrawn consent
# ---------------------------------------------------------------------------

class TestWithdrawnConsent:
    def test_withdrawn_client_is_blocked(self):
        clients = _clients(
            {"client_id": "CLI-W", "current_consent_id": "CON-W"},
            {"client_id": "CLI-A", "current_consent_id": "CON-A"},
        )
        consent = _consent(
            {"consent_id": "CON-W", "client_id": "CLI-W", "status": "withdrawn"},
            {"consent_id": "CON-A", "client_id": "CLI-A", "status": "active"},
        )
        gate = _gate(clients, consent)
        allowed, blocked = gate.filter_clients(clients)

        assert "CLI-W" not in allowed["client_id"].values
        assert "CLI-W" in blocked["client_id"].values
        assert blocked.loc[blocked["client_id"] == "CLI-W", "block_reason"].iloc[0] == BLOCK_WITHDRAWN

    def test_active_client_not_blocked(self):
        clients = _clients(
            {"client_id": "CLI-W", "current_consent_id": "CON-W"},
            {"client_id": "CLI-A", "current_consent_id": "CON-A"},
        )
        consent = _consent(
            {"consent_id": "CON-W", "client_id": "CLI-W", "status": "withdrawn"},
            {"consent_id": "CON-A", "client_id": "CLI-A", "status": "active"},
        )
        gate = _gate(clients, consent)
        allowed, _ = gate.filter_clients(clients)

        assert "CLI-A" in allowed["client_id"].values


# ---------------------------------------------------------------------------
# 7c — Expired consent
# ---------------------------------------------------------------------------

class TestExpiredConsent:
    def test_expired_client_is_blocked(self):
        clients = _clients({"client_id": "CLI-E", "current_consent_id": "CON-E"})
        consent = _consent({"consent_id": "CON-E", "client_id": "CLI-E",
                            "status": "active", "expiry_date": str(YESTERDAY)})
        gate = _gate(clients, consent)
        allowed, blocked = gate.filter_clients(clients)

        assert "CLI-E" not in allowed["client_id"].values
        assert "CLI-E" in blocked["client_id"].values
        assert blocked.loc[blocked["client_id"] == "CLI-E", "block_reason"].iloc[0] == BLOCK_EXPIRED

    def test_expiry_today_is_not_blocked(self):
        """Expiry must be strictly < reference_date to be blocked."""
        clients = _clients({"client_id": "CLI-E", "current_consent_id": "CON-E"})
        consent = _consent({"consent_id": "CON-E", "client_id": "CLI-E",
                            "status": "active", "expiry_date": str(TODAY)})
        gate = _gate(clients, consent)
        allowed, blocked = gate.filter_clients(clients)

        assert "CLI-E" in allowed["client_id"].values
        assert "CLI-E" not in blocked["client_id"].values


# ---------------------------------------------------------------------------
# 7d — OCAP protection
# ---------------------------------------------------------------------------

class TestOcapProtection:
    def _ocap_clients_consent(self):
        clients = _clients({"client_id": "CLI-OCAP", "current_consent_id": "CON-OCAP",
                            "ocap_protected": True})
        consent = _consent({"consent_id": "CON-OCAP", "client_id": "CLI-OCAP",
                            "status": "active", "sharing_scope_agency_ids": "ORG-APPROVED"})
        return clients, consent

    def test_ocap_blocked_from_unauthorized_org(self):
        clients, consent = self._ocap_clients_consent()
        gate = _gate(clients, consent, viewing_org_id="ORG-OTHER")
        allowed, blocked = gate.filter_clients(clients)

        assert "CLI-OCAP" not in allowed["client_id"].values
        assert "CLI-OCAP" in blocked["client_id"].values
        assert blocked.loc[blocked["client_id"] == "CLI-OCAP", "block_reason"].iloc[0] == BLOCK_OCAP

    def test_ocap_allowed_for_approved_org(self):
        clients, consent = self._ocap_clients_consent()
        gate = _gate(clients, consent, viewing_org_id="ORG-APPROVED")
        allowed, blocked = gate.filter_clients(clients)

        assert "CLI-OCAP" in allowed["client_id"].values
        assert "CLI-OCAP" not in blocked["client_id"].values

    def test_ocap_system_view_does_not_hard_block(self):
        """viewing_org_id=None is the system/admin view — OCAP not hard-blocked."""
        clients, consent = self._ocap_clients_consent()
        gate = _gate(clients, consent, viewing_org_id=None)
        allowed, blocked = gate.filter_clients(clients)

        assert "CLI-OCAP" in allowed["client_id"].values


# ---------------------------------------------------------------------------
# 7e — Single-agency scope
# ---------------------------------------------------------------------------

class TestSingleAgencyScope:
    def _sa_clients_consent(self):
        clients = _clients({"client_id": "CLI-SA", "current_consent_id": "CON-SA"})
        consent = _consent({"consent_id": "CON-SA", "client_id": "CLI-SA",
                            "status": "active", "sharing_scope_type": "org"})
        return clients, consent

    def test_single_agency_blocked_in_multi_org_view(self):
        clients, consent = self._sa_clients_consent()
        gate = _gate(clients, consent)
        allowed, blocked = gate.filter_clients(clients, multi_org_view=True)

        assert "CLI-SA" not in allowed["client_id"].values
        assert "CLI-SA" in blocked["client_id"].values
        assert blocked.loc[blocked["client_id"] == "CLI-SA", "block_reason"].iloc[0] == BLOCK_SINGLE_AGENCY

    def test_single_agency_allowed_in_single_org_view(self):
        clients, consent = self._sa_clients_consent()
        gate = _gate(clients, consent)
        allowed, blocked = gate.filter_clients(clients, multi_org_view=False)

        assert "CLI-SA" in allowed["client_id"].values
        assert "CLI-SA" not in blocked["client_id"].values


# ---------------------------------------------------------------------------
# 7f — FOIPPA missing purpose_codes
# ---------------------------------------------------------------------------

class TestFoippa:
    def _foippa_setup(self):
        clients = _clients({"client_id": "CLI-F", "current_consent_id": "CON-F"})
        consent = _consent({
            "consent_id": "CON-F", "client_id": "CLI-F",
            "status": "active",
            "legal_basis": "public_body",
            "purpose_codes": "",          # empty — FOIPPA violation
        })
        referrals = pd.DataFrame([{
            "referral_id": "REF-F",
            "client_id": "CLI-F",
            "consent_record_id": "CON-F",
            "status": "submitted",
            "submitted_at": pd.Timestamp("2026-04-01"),
            "referring_org_id": "ORG-1",
            "receiving_org_id": "ORG-2",
            "referral_type": "housing",
            "referral_reason": "test",
            "referral_priority": "high",
        }])
        return clients, consent, referrals

    def test_foippa_flagged_in_get_violations(self):
        clients, consent, referrals = self._foippa_setup()
        gate = ConsentGate(clients, consent, referrals_df=referrals,
                           reference_date=TODAY)
        violations = gate.get_violations()
        foippa_violations = violations[
            violations["violation_type"].str.contains("FOIPPA", case=False, na=False)
        ]
        assert len(foippa_violations) > 0

    def test_foippa_referral_blocked_by_filter_referrals(self):
        clients, consent, referrals = self._foippa_setup()
        gate = ConsentGate(clients, consent, referrals_df=referrals,
                           reference_date=TODAY)
        allowed, blocked = gate.filter_referrals(referrals)

        assert "REF-F" not in allowed["referral_id"].values
        assert "REF-F" in blocked["referral_id"].values
        assert blocked.loc[blocked["referral_id"] == "REF-F", "block_reason"].iloc[0] == BLOCK_FOIPPA_NO_PURPOSE


# ---------------------------------------------------------------------------
# OCAP edge cases — empty partner list, multi-partner semicolons, padding
# ---------------------------------------------------------------------------

class TestOcapEdgeCases:
    def test_ocap_empty_partner_list_blocked_from_any_viewing_org(self):
        """Empty sharing_scope_agency_ids means NO org can access the OCAP client."""
        clients = _clients({"client_id": "CLI-OCAP", "current_consent_id": "CON-OCAP",
                            "ocap_protected": True})
        consent = _consent({"consent_id": "CON-OCAP", "client_id": "CLI-OCAP",
                            "status": "active", "sharing_scope_agency_ids": ""})
        gate = _gate(clients, consent, viewing_org_id="ORG-ANYONE")
        allowed, blocked = gate.filter_clients(clients)

        assert "CLI-OCAP" in blocked["client_id"].values
        assert blocked.loc[blocked["client_id"] == "CLI-OCAP", "block_reason"].iloc[0] == BLOCK_OCAP

    def test_ocap_viewing_org_in_semicolon_list_allowed(self):
        """Viewing org that IS one of the semicolon-separated approved orgs is allowed."""
        clients = _clients({"client_id": "CLI-OCAP", "current_consent_id": "CON-OCAP",
                            "ocap_protected": True})
        consent = _consent({"consent_id": "CON-OCAP", "client_id": "CLI-OCAP",
                            "status": "active",
                            "sharing_scope_agency_ids": "ORG-A;ORG-B;ORG-C"})
        gate = _gate(clients, consent, viewing_org_id="ORG-B")
        allowed, blocked = gate.filter_clients(clients)

        assert "CLI-OCAP" in allowed["client_id"].values
        assert "CLI-OCAP" not in blocked["client_id"].values

    def test_ocap_viewing_org_not_in_semicolon_list_blocked(self):
        """Viewing org NOT in semicolon-separated list is blocked."""
        clients = _clients({"client_id": "CLI-OCAP", "current_consent_id": "CON-OCAP",
                            "ocap_protected": True})
        consent = _consent({"consent_id": "CON-OCAP", "client_id": "CLI-OCAP",
                            "status": "active",
                            "sharing_scope_agency_ids": "ORG-A;ORG-B;ORG-C"})
        gate = _gate(clients, consent, viewing_org_id="ORG-D")
        allowed, blocked = gate.filter_clients(clients)

        assert "CLI-OCAP" in blocked["client_id"].values
        assert blocked.loc[blocked["client_id"] == "CLI-OCAP", "block_reason"].iloc[0] == BLOCK_OCAP


# ---------------------------------------------------------------------------
# filter_referrals — client-level consent inheritance and per-referral checks
# ---------------------------------------------------------------------------

class TestFilterReferralsInheritance:
    def _ref(self, referral_id: str, client_id: str, consent_record_id: str | None = None) -> dict:
        return {
            "referral_id": referral_id,
            "client_id": client_id,
            "consent_record_id": consent_record_id,
            "status": "submitted",
            "submitted_at": pd.Timestamp("2026-04-01"),
            "referring_org_id": "ORG-1",
            "receiving_org_id": "ORG-2",
        }

    def test_referral_for_withdrawn_client_blocked(self):
        clients = _clients({"client_id": "CLI-W", "current_consent_id": "CON-W"})
        consent = _consent({"consent_id": "CON-W", "client_id": "CLI-W", "status": "withdrawn"})
        referrals = pd.DataFrame([self._ref("REF-W", "CLI-W", "CON-W")])
        gate = _gate(clients, consent)
        allowed, blocked = gate.filter_referrals(referrals)

        assert "REF-W" not in allowed["referral_id"].values
        assert "REF-W" in blocked["referral_id"].values
        assert blocked.loc[blocked["referral_id"] == "REF-W", "block_reason"].iloc[0] == BLOCK_WITHDRAWN

    def test_referral_for_expired_client_blocked(self):
        clients = _clients({"client_id": "CLI-E", "current_consent_id": "CON-E"})
        consent = _consent({"consent_id": "CON-E", "client_id": "CLI-E",
                            "status": "active", "expiry_date": str(YESTERDAY)})
        referrals = pd.DataFrame([self._ref("REF-E", "CLI-E", "CON-E")])
        gate = _gate(clients, consent)
        allowed, blocked = gate.filter_referrals(referrals)

        assert "REF-E" in blocked["referral_id"].values
        assert blocked.loc[blocked["referral_id"] == "REF-E", "block_reason"].iloc[0] == BLOCK_EXPIRED

    def test_referral_for_active_client_allowed(self):
        clients = _clients({"client_id": "CLI-A", "current_consent_id": "CON-A"})
        consent = _consent({"consent_id": "CON-A", "client_id": "CLI-A", "status": "active"})
        referrals = pd.DataFrame([self._ref("REF-A", "CLI-A", "CON-A")])
        gate = _gate(clients, consent)
        allowed, blocked = gate.filter_referrals(referrals)

        assert "REF-A" in allowed["referral_id"].values
        assert "REF-A" not in blocked["referral_id"].values

    def test_foippa_legal_obligation_also_blocks_referral(self):
        """`legal_basis='legal_obligation'` with empty purpose_codes must also be blocked."""
        clients = _clients({"client_id": "CLI-LO", "current_consent_id": "CON-LO"})
        consent = _consent({
            "consent_id": "CON-LO", "client_id": "CLI-LO",
            "status": "active",
            "legal_basis": "legal_obligation",
            "purpose_codes": "",
        })
        referrals = pd.DataFrame([self._ref("REF-LO", "CLI-LO", "CON-LO")])
        gate = _gate(clients, consent)
        allowed, blocked = gate.filter_referrals(referrals)

        assert "REF-LO" in blocked["referral_id"].values
        assert blocked.loc[blocked["referral_id"] == "REF-LO", "block_reason"].iloc[0] == BLOCK_FOIPPA_NO_PURPOSE

    def test_single_agency_referral_blocked_by_default_multi_org_view(self):
        """`filter_referrals` defaults to multi_org_view=True — single-agency clients blocked."""
        clients = _clients({"client_id": "CLI-SA", "current_consent_id": "CON-SA"})
        consent = _consent({"consent_id": "CON-SA", "client_id": "CLI-SA",
                            "status": "active", "sharing_scope_type": "org"})
        referrals = pd.DataFrame([self._ref("REF-SA", "CLI-SA", "CON-SA")])
        gate = _gate(clients, consent)
        # Default multi_org_view=True
        allowed, blocked = gate.filter_referrals(referrals)

        assert "REF-SA" in blocked["referral_id"].values
        assert blocked.loc[blocked["referral_id"] == "REF-SA", "block_reason"].iloc[0] == BLOCK_SINGLE_AGENCY


# ---------------------------------------------------------------------------
# get_violations — all 6 violation types
# ---------------------------------------------------------------------------

class TestGetViolations:
    def test_withdrawn_with_active_encounter_is_critical(self):
        """Active encounter for withdrawn client → RED_FLAG_WITHDRAWN_CONSENT_ACTIVE_ENCOUNTER."""
        clients = _clients({"client_id": "CLI-W", "current_consent_id": "CON-W"})
        consent = _consent({"consent_id": "CON-W", "client_id": "CLI-W", "status": "withdrawn"})
        encounters = pd.DataFrame([{
            "encounter_id": "ENC-1", "client_id": "CLI-W",
            "org_id": "ORG-1", "status": "active",
        }])
        gate = ConsentGate(clients, consent, encounters_df=encounters, reference_date=TODAY)
        violations = gate.get_violations()

        match = violations[violations["violation_type"] == "RED_FLAG_WITHDRAWN_CONSENT_ACTIVE_ENCOUNTER"]
        assert len(match) > 0
        assert match.iloc[0]["severity"] == "critical"
        assert match.iloc[0]["client_id"] == "CLI-W"

    def test_expired_consent_flagged(self):
        """Expired consent → RED_FLAG_EXPIRED_CONSENT_USED (critical)."""
        clients = _clients({"client_id": "CLI-E", "current_consent_id": "CON-E"})
        consent = _consent({"consent_id": "CON-E", "client_id": "CLI-E",
                            "status": "active", "expiry_date": str(YESTERDAY)})
        gate = _gate(clients, consent)
        violations = gate.get_violations()

        match = violations[violations["violation_type"] == "RED_FLAG_EXPIRED_CONSENT_USED"]
        assert len(match) > 0
        assert match.iloc[0]["severity"] == "critical"

    def test_ocap_no_approved_partners_is_critical(self):
        """OCAP client with empty sharing_scope_agency_ids → RED_FLAG_OCAP_NO_APPROVED_PARTNERS."""
        clients = _clients({"client_id": "CLI-OCAP", "current_consent_id": "CON-OCAP",
                            "ocap_protected": True})
        consent = _consent({"consent_id": "CON-OCAP", "client_id": "CLI-OCAP",
                            "status": "active", "sharing_scope_agency_ids": ""})
        gate = _gate(clients, consent)
        violations = gate.get_violations()

        match = violations[violations["violation_type"] == "RED_FLAG_OCAP_NO_APPROVED_PARTNERS"]
        assert len(match) > 0
        assert match.iloc[0]["severity"] == "critical"

    def test_scope_mismatch_is_warning(self):
        """Single-agency client in inter-org referrals → RED_FLAG_SCOPE_MISMATCH (warning)."""
        clients = _clients({"client_id": "CLI-SA", "current_consent_id": "CON-SA"})
        consent = _consent({"consent_id": "CON-SA", "client_id": "CLI-SA",
                            "status": "active", "sharing_scope_type": "org"})
        referrals = pd.DataFrame([{
            "referral_id": "REF-SM", "client_id": "CLI-SA",
            "consent_record_id": "CON-SA", "status": "submitted",
            "submitted_at": pd.Timestamp("2026-04-01"),
            "referring_org_id": "ORG-1", "receiving_org_id": "ORG-2",
        }])
        gate = ConsentGate(clients, consent, referrals_df=referrals, reference_date=TODAY)
        violations = gate.get_violations()

        match = violations[violations["violation_type"] == "RED_FLAG_SCOPE_MISMATCH"]
        assert len(match) > 0
        assert match.iloc[0]["severity"] == "warning"

    def test_seeded_red_flag_note_extracted(self):
        """Consent row with RED_FLAG_ tag in notes column → violation surfaced."""
        clients = _clients({"client_id": "CLI-N", "current_consent_id": "CON-N"})
        consent_df = _consent({"consent_id": "CON-N", "client_id": "CLI-N", "status": "active"})
        consent_df["notes"] = "RED_FLAG_OCAP_OVERRIDE caseworker bypassed flag manually"
        gate = _gate(clients, consent_df)
        violations = gate.get_violations()

        match = violations[violations["violation_type"] == "RED_FLAG_OCAP_OVERRIDE"]
        assert len(match) > 0

    def test_clean_data_returns_empty_violations_with_correct_columns(self):
        """No violations in clean data → empty DataFrame with required columns."""
        clients = _clients({"client_id": "CLI-OK", "current_consent_id": "CON-OK"})
        consent = _consent({"consent_id": "CON-OK", "client_id": "CLI-OK", "status": "active"})
        gate = _gate(clients, consent)
        violations = gate.get_violations()

        assert violations.empty
        for col in ("violation_type", "client_id", "severity"):
            assert col in violations.columns


# ---------------------------------------------------------------------------
# Fallback consent resolution — null current_consent_id
# ---------------------------------------------------------------------------

class TestConsentFallback:
    def test_null_current_consent_id_uses_most_recent_record(self):
        """Client with no current_consent_id falls back to most recently given consent."""
        clients = _clients({"client_id": "CLI-FB", "current_consent_id": None})
        consent = _consent(
            {"consent_id": "CON-OLD", "client_id": "CLI-FB", "status": "active",
             "given_date": "2024-01-01", "expiry_date": str(TOMORROW)},
            {"consent_id": "CON-NEW", "client_id": "CLI-FB", "status": "active",
             "given_date": "2025-06-01", "expiry_date": str(TOMORROW)},
        )
        gate = _gate(clients, consent)
        allowed, blocked = gate.filter_clients(clients)

        # Most recent consent is active → client allowed
        assert "CLI-FB" in allowed["client_id"].values
        assert "CLI-FB" not in blocked["client_id"].values

    def test_null_current_consent_id_withdrawn_via_fallback_blocks_client(self):
        """Withdrawn status discovered through fallback consent lookup blocks the client."""
        clients = _clients({"client_id": "CLI-FB2", "current_consent_id": None})
        consent = _consent({
            "consent_id": "CON-W2", "client_id": "CLI-FB2",
            "status": "withdrawn", "given_date": "2025-12-01",
        })
        gate = _gate(clients, consent)
        allowed, blocked = gate.filter_clients(clients)

        assert "CLI-FB2" in blocked["client_id"].values
        assert blocked.loc[blocked["client_id"] == "CLI-FB2", "block_reason"].iloc[0] == BLOCK_WITHDRAWN


# ---------------------------------------------------------------------------
# Block priority and mixed-set correctness
# ---------------------------------------------------------------------------

class TestBlockPriority:
    def test_only_bad_consent_clients_blocked_in_mixed_set(self):
        """3 clients: withdrawn, expired, and active. Only the first two are blocked."""
        clients = _clients(
            {"client_id": "CLI-W",  "current_consent_id": "CON-W"},
            {"client_id": "CLI-E",  "current_consent_id": "CON-E"},
            {"client_id": "CLI-OK", "current_consent_id": "CON-OK"},
        )
        consent = _consent(
            {"consent_id": "CON-W",  "client_id": "CLI-W",  "status": "withdrawn"},
            {"consent_id": "CON-E",  "client_id": "CLI-E",  "status": "active",
             "expiry_date": str(YESTERDAY)},
            {"consent_id": "CON-OK", "client_id": "CLI-OK", "status": "active"},
        )
        gate = _gate(clients, consent)
        allowed, blocked = gate.filter_clients(clients)

        assert set(allowed["client_id"].values) == {"CLI-OK"}
        assert set(blocked["client_id"].values) == {"CLI-W", "CLI-E"}

    def test_withdrawn_takes_priority_over_expired_block_reason(self):
        """A consent that is both withdrawn AND past expiry_date is blocked as WITHDRAWN,
        not EXPIRED, and appears exactly once in the blocked output."""
        clients = _clients({"client_id": "CLI-WE", "current_consent_id": "CON-WE"})
        consent = _consent({"consent_id": "CON-WE", "client_id": "CLI-WE",
                            "status": "withdrawn", "expiry_date": str(YESTERDAY)})
        gate = _gate(clients, consent)
        _, blocked = gate.filter_clients(clients)

        rows_for_client = blocked[blocked["client_id"] == "CLI-WE"]
        assert len(rows_for_client) == 1
        assert rows_for_client.iloc[0]["block_reason"] == BLOCK_WITHDRAWN
