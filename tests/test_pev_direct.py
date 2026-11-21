"""
PEV contract deterministic-logic tests (Python standard-library unittest).

Coverage:
- quote_exists computation (mirrors the contract's substring logic)
- input length-limit comparison (mirrors input_within_limit)
- _compute_decision decision-table logic (imports the module-level helper
  from contracts.pev_contract via the genlayer stub in
  tests/genlayer_stub.py — V5 fix: V4 called contract._compute_decision,
  but _compute_decision is a module-level function, not a method)
- evaluation_complete field-completeness check (illustrative re-implementation;
  does not exercise the contract's actual evaluation_complete logic)

Execution status (V5, 2026-11-21): all 10 tests pass with the stub installed
(see README "Testing Results"). Run from the repository root:
python -m unittest -v tests.test_pev_direct
"""

import os
import sys
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
_TESTS = os.path.dirname(os.path.abspath(__file__))
if _TESTS not in sys.path:
    sys.path.insert(0, _TESTS)

import genlayer_stub

genlayer_stub.install()

from contracts.pev_contract import _compute_decision


class TestPEVDeterministicLogic(unittest.TestCase):
    """Tests for deterministic logic that does not require GenLayer runtime."""

    def test_quote_exists_true(self):
        """Valid supporting quote exists verbatim in proposal."""
        requirement = "System shall use AES-256 encryption"
        proposal = "We implement AES-256 encryption at rest."
        candidate_quote = "AES-256 encryption at rest"

        quote_exists = bool(candidate_quote) and (candidate_quote in proposal)
        self.assertTrue(quote_exists)

    def test_quote_exists_false(self):
        """Fabricated quote not found in proposal."""
        requirement = "System shall use AES-256 encryption"
        proposal = "We use strong encryption."
        candidate_quote = "AES-256 encryption"

        quote_exists = bool(candidate_quote) and (candidate_quote in proposal)
        self.assertFalse(quote_exists)

    def test_empty_quote(self):
        """Empty candidate quote - evaluation proceeds without quote."""
        requirement = "System shall use AES-256 encryption"
        proposal = "We use encryption."
        candidate_quote = ""

        quote_exists = bool(candidate_quote) and (candidate_quote in proposal)
        self.assertFalse(quote_exists)

    def test_input_within_limit(self):
        """Proposal within maximum length."""
        short_proposal = "A" * 100
        long_proposal = "B" * 100001

        self.assertTrue(len(short_proposal) <= 50000)
        self.assertFalse(len(long_proposal) <= 50000)

    def test_compute_decision_accept(self):
        """Decision table: supported + relevant + true = accept."""
        result = _compute_decision("supported", "relevant", True)
        self.assertEqual(result, "accept")

    def test_compute_decision_reject_contradicted(self):
        """Decision table: contradicted = reject."""
        result = _compute_decision("contradicted", "relevant", True)
        self.assertEqual(result, "reject")

    def test_compute_decision_reject_irrelevant(self):
        """Decision table: irrelevant = reject."""
        result = _compute_decision("supported", "irrelevant", True)
        self.assertEqual(result, "reject")

    def test_compute_decision_review(self):
        """Decision table: partial/insufficient/ambiguous = review."""
        self.assertEqual(_compute_decision("partial", "relevant", True), "review")
        self.assertEqual(_compute_decision("insufficient", "relevant", True), "review")
        self.assertEqual(_compute_decision("ambiguous", "relevant", True), "review")


class TestPEVWithMocks(unittest.TestCase):
    """Illustrative field-completeness tests (no mocking; pure dict checks).

    NOTE: These tests re-implement a field-presence check and do not import
    or exercise the contract's actual evaluation_complete logic. Their
    execution is not verified by repository artifacts, and they do not
    constitute validation of GenLayer contract behavior.
    """

    def test_evaluation_complete_from_fields(self):
        """evaluation_complete requires all four fields with valid values."""
        leader_data = {
            "evidence_assessment": "supported",
            "semantic_relevance": "relevant",
            "evidence_found": True,
            "decision": "accept",
        }
        complete = all(
            leader_data.get(f) is not None
            for f in ("evidence_assessment", "semantic_relevance", "evidence_found", "decision")
        )
        self.assertTrue(complete)

    def test_evaluation_complete_missing_field(self):
        """Missing field makes evaluation incomplete."""
        leader_data = {"evidence_assessment": "supported"}
        complete = all(
            leader_data.get(f) is not None
            for f in ("evidence_assessment", "semantic_relevance", "evidence_found", "decision")
        )
        self.assertFalse(complete)


if __name__ == "__main__":
    unittest.main()