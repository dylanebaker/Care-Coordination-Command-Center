# Pytest Results

**Project:** Care Coordination Command Center

**Summary:**

- Total tests collected: **59**
- Passed: **59**
- Failed: **0**
- Duration: **1.80s**

**Run output:**

```
======================================================== test session starts =========================================================

tests/test_consent_gate.py::TestWithdrawnConsent::test_withdrawn_client_is_blocked PASSED                                       [  1%]
tests/test_consent_gate.py::TestWithdrawnConsent::test_active_client_not_blocked PASSED                                         [  3%]
tests/test_consent_gate.py::TestExpiredConsent::test_expired_client_is_blocked PASSED                                           [  5%]
tests/test_consent_gate.py::TestExpiredConsent::test_expiry_today_is_not_blocked PASSED                                         [  6%]
tests/test_consent_gate.py::TestOcapProtection::test_ocap_blocked_from_unauthorized_org PASSED                                  [  8%]
tests/test_consent_gate.py::TestOcapProtection::test_ocap_allowed_for_approved_org PASSED                                       [ 10%]
tests/test_consent_gate.py::TestOcapProtection::test_ocap_system_view_does_not_hard_block PASSED                                [ 11%]
tests/test_consent_gate.py::TestSingleAgencyScope::test_single_agency_blocked_in_multi_org_view PASSED                          [ 13%]
tests/test_consent_gate.py::TestSingleAgencyScope::test_single_agency_allowed_in_single_org_view PASSED                         [ 15%]
tests/test_consent_gate.py::TestFoippa::test_foippa_flagged_in_get_violations PASSED                                            [ 16%]
tests/test_consent_gate.py::TestFoippa::test_foippa_referral_blocked_by_filter_referrals PASSED                                 [ 18%]
tests/test_consent_gate.py::TestOcapEdgeCases::test_ocap_empty_partner_list_blocked_from_any_viewing_org PASSED                 [ 20%]
tests/test_consent_gate.py::TestOcapEdgeCases::test_ocap_viewing_org_in_semicolon_list_allowed PASSED                           [ 22%]
tests/test_consent_gate.py::TestOcapEdgeCases::test_ocap_viewing_org_not_in_semicolon_list_blocked PASSED                       [ 23%]
tests/test_consent_gate.py::TestFilterReferralsInheritance::test_referral_for_withdrawn_client_blocked PASSED                   [ 25%]
tests/test_consent_gate.py::TestFilterReferralsInheritance::test_referral_for_expired_client_blocked PASSED                     [ 27%]
tests/test_consent_gate.py::TestFilterReferralsInheritance::test_referral_for_active_client_allowed PASSED                      [ 28%]
tests/test_consent_gate.py::TestFilterReferralsInheritance::test_foippa_legal_obligation_also_blocks_referral PASSED            [ 30%]
tests/test_consent_gate.py::TestFilterReferralsInheritance::test_single_agency_referral_blocked_by_default_multi_org_view PASSED [ 32%]
tests/test_consent_gate.py::TestGetViolations::test_withdrawn_with_active_encounter_is_critical PASSED                          [ 33%]
tests/test_consent_gate.py::TestGetViolations::test_expired_consent_flagged PASSED                                              [ 35%]
tests/test_consent_gate.py::TestGetViolations::test_ocap_no_approved_partners_is_critical PASSED                                [ 37%]
tests/test_consent_gate.py::TestGetViolations::test_scope_mismatch_is_warning PASSED                                            [ 38%]
tests/test_consent_gate.py::TestGetViolations::test_seeded_red_flag_note_extracted PASSED                                       [ 40%]
tests/test_consent_gate.py::TestGetViolations::test_clean_data_returns_empty_violations_with_correct_columns PASSED             [ 42%]
tests/test_consent_gate.py::TestConsentFallback::test_null_current_consent_id_uses_most_recent_record PASSED                    [ 44%]
tests/test_consent_gate.py::TestConsentFallback::test_null_current_consent_id_withdrawn_via_fallback_blocks_client PASSED       [ 45%]
tests/test_consent_gate.py::TestBlockPriority::test_only_bad_consent_clients_blocked_in_mixed_set PASSED                        [ 47%]
tests/test_consent_gate.py::TestBlockPriority::test_withdrawn_takes_priority_over_expired_block_reason PASSED                   [ 49%]
tests/test_risk_scorer.py::TestScoreClientsGateIntegration::test_withdrawn_client_not_in_scored_output PASSED                   [ 50%]
tests/test_risk_scorer.py::TestScoreClientsGateIntegration::test_scored_output_has_risk_columns PASSED                          [ 52%]
tests/test_risk_scorer.py::TestRiskFactorScoring::test_baseline_scores_zero PASSED                                              [ 54%]
tests/test_risk_scorer.py::TestRiskFactorScoring::test_bnl_active_flag PASSED                                                   [ 55%]
tests/test_risk_scorer.py::TestRiskFactorScoring::test_bnl_status_active PASSED                                                 [ 57%]
tests/test_risk_scorer.py::TestRiskFactorScoring::test_chronic_homeless PASSED                                                  [ 59%]
tests/test_risk_scorer.py::TestRiskFactorScoring::test_ca_priority_p3 PASSED                                                    [ 61%]
tests/test_risk_scorer.py::TestRiskFactorScoring::test_ca_priority_p2 PASSED                                                    [ 62%]
tests/test_risk_scorer.py::TestRiskFactorScoring::test_ca_priority_p1 PASSED                                                    [ 64%]
tests/test_risk_scorer.py::TestRiskFactorScoring::test_acuity_very_high PASSED                                                  [ 66%]
tests/test_risk_scorer.py::TestRiskFactorScoring::test_acuity_high PASSED                                                       [ 67%]
tests/test_risk_scorer.py::TestRiskFactorScoring::test_acuity_low_scores_zero PASSED                                            [ 69%]
tests/test_risk_scorer.py::TestRiskFactorScoring::test_lost_contact_over_90_days PASSED                                         [ 71%]
tests/test_risk_scorer.py::TestRiskFactorScoring::test_lost_contact_exactly_90_days_triggers_30_bucket PASSED                   [ 72%]
tests/test_risk_scorer.py::TestRiskFactorScoring::test_lost_contact_31_to_90_days PASSED                                        [ 74%]
tests/test_risk_scorer.py::TestRiskFactorScoring::test_lost_contact_30_days_does_not_trigger PASSED                             [ 76%]
tests/test_risk_scorer.py::TestRiskFactorScoring::test_stalled_referral_submitted_status PASSED                                 [ 77%]
tests/test_risk_scorer.py::TestRiskFactorScoring::test_stalled_referral_pending_status PASSED                                   [ 79%]
tests/test_risk_scorer.py::TestRiskFactorScoring::test_recent_referral_not_stalled PASSED                                       [ 81%]
tests/test_risk_scorer.py::TestRiskFactorScoring::test_closed_referral_never_stalled PASSED                                     [ 83%]
tests/test_risk_scorer.py::TestRiskFactorScoring::test_consent_expiring_within_warning_window PASSED                            [ 84%]
tests/test_risk_scorer.py::TestRiskFactorScoring::test_consent_expiring_on_last_day_of_window PASSED                            [ 86%]
tests/test_risk_scorer.py::TestRiskFactorScoring::test_consent_not_expiring_on_boundary_day PASSED                              [ 88%]
tests/test_risk_scorer.py::TestRiskFactorScoring::test_has_violation_adds_score PASSED                                          [ 89%]
tests/test_risk_scorer.py::TestRiskFactorScoring::test_no_violation_for_other_client_id PASSED                                  [ 91%]
tests/test_risk_scorer.py::TestRiskTierThresholds::test_score_65_is_critical PASSED                                             [ 93%]
tests/test_risk_scorer.py::TestRiskTierThresholds::test_score_40_is_high PASSED                                                 [ 94%]
tests/test_risk_scorer.py::TestRiskTierThresholds::test_score_20_is_medium PASSED                                               [ 96%]
tests/test_risk_scorer.py::TestRiskTierThresholds::test_score_5_is_low PASSED                                                   [ 98%]
tests/test_risk_scorer.py::TestScoreCap::test_score_capped_at_100 PASSED                                                        [100%]

========================================================= 59 passed in 1.80s =========================================================
```

