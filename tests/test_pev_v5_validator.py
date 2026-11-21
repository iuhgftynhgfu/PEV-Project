"""PEV V5 validator tests — rejection-scenario coverage (stdlib unittest).

These tests exercise the V5 redesign that answers the Oct 31, 2026
rejection of the V4 submission: V4's validator only checked the leader
result's structure, so opposite assessments (supported -> accept vs
contradicted -> reject) for the same proposal BOTH passed. V5's validator
independently re-evaluates the proposal evidence with its own LLM call and
accepts the leader's result only when the bound (assessment, decision)
pair agrees with its own.

The tests run against a stdlib-only `genlayer` stub (tests/genlayer_stub.py)
injected into sys.modules before the contract is imported. The stub's
exec_prompt is scripted: each test queues the exact LLM responses the
leader and the validator "receive", so every scenario is deterministic and
needs no runtime, wallet, or paid service.

Coverage (spec section 4.2):
1. Opposite assessments must NOT both pass (both directions).
2. Agreement passes (accept and reject).
3. Review-class equivalence (partial/insufficient/ambiguous agree; a
   review label vs a decisive label disagrees).
4. Broken validator output disagrees (malformed JSON, missing fields,
   invalid enum).
5. Structural checks retained (decision-table inconsistency, quote_exists
   mismatch, non-Return leader result, cross-field inconsistency).
6. End-to-end via stubbed run_nondet_unsafe: agreement stores the
   evaluation (and leader/validator prompts are byte-identical);
   disagreement stores nothing.
7. Decision-table rows are covered by the fixed tests in
   tests/test_pev_direct.py (they import the module-level helper directly).

Run from the repository root: python -m unittest -v tests.test_pev_v5_validator
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

stub = genlayer_stub.install()

from contracts.pev_contract import (
    PEVContract,
    _compute_decision,
    _validator_fn,
)

REQUIREMENT = "System shall use AES-256 encryption"
PROPOSAL = "We implement AES-256 encryption at rest."
QUOTE = "AES-256 encryption at rest"


def _leader_result(ea, sr, ef, decision=None, quote_exists=True, explanation=""):
    """Build a leader result dict, deriving the decision unless overridden."""
    if decision is None:
        decision = _compute_decision(ea, sr, ef)
    return {
        "evidence_assessment": ea,
        "semantic_relevance": sr,
        "evidence_found": ef,
        "explanation": explanation,
        "decision": decision,
        "quote_exists": quote_exists,
    }


def _llm_response(ea, sr, ef, explanation=""):
    """Build a scripted exec_prompt response (evidence fields only)."""
    return {
        "evidence_assessment": ea,
        "semantic_relevance": sr,
        "evidence_found": ef,
        "explanation": explanation,
    }


class TestV5Validator(unittest.TestCase):
    """Direct validator tests with a hand-crafted leader result."""

    def setUp(self):
        stub.reset()

    def _validate(self, leader_data, validator_response, quote_exists=True):
        """Run _validator_fn with one scripted validator LLM response."""
        if validator_response is not None:
            stub.queue_responses([validator_response])
        return _validator_fn(
            stub.vm.Return(leader_data), REQUIREMENT, PROPOSAL, QUOTE, quote_exists
        )

    # -- 1. Opposite assessments must NOT both pass (the rejection case) --

    def test_opposite_supported_leader_contradicted_validator(self):
        """Leader supported->accept, validator contradicted->reject: False."""
        leader = _leader_result("supported", "relevant", True)
        validator = _llm_response("contradicted", "relevant", True)
        self.assertFalse(self._validate(leader, validator))

    def test_opposite_contradicted_leader_supported_validator(self):
        """Leader contradicted->reject, validator supported->accept: False."""
        leader = _leader_result("contradicted", "relevant", True)
        validator = _llm_response("supported", "relevant", True)
        self.assertFalse(self._validate(leader, validator))

    # -- 2. Agreement passes --

    def test_agreement_accept(self):
        """Leader and validator both supported->accept: True."""
        leader = _leader_result("supported", "relevant", True)
        validator = _llm_response("supported", "relevant", True)
        self.assertTrue(self._validate(leader, validator))

    def test_agreement_reject(self):
        """Leader and validator both contradicted->reject: True."""
        leader = _leader_result("contradicted", "relevant", True)
        validator = _llm_response("contradicted", "relevant", True)
        self.assertTrue(self._validate(leader, validator))

    def test_agreement_reject_irrelevant(self):
        """Leader and validator both irrelevant->reject: True."""
        leader = _leader_result("partial", "irrelevant", True)
        validator = _llm_response("partial", "irrelevant", True)
        self.assertTrue(self._validate(leader, validator))

    # -- 3. Review-class equivalence --

    def test_review_class_partial_vs_insufficient(self):
        """Leader partial->review, validator insufficient->review: True."""
        leader = _leader_result("partial", "relevant", True)
        validator = _llm_response("insufficient", "relevant", True)
        self.assertTrue(self._validate(leader, validator))

    def test_review_class_insufficient_vs_ambiguous(self):
        """Leader insufficient->review, validator ambiguous->review: True."""
        leader = _leader_result("insufficient", "relevant", True)
        validator = _llm_response("ambiguous", "uncertain", False)
        self.assertTrue(self._validate(leader, validator))

    def test_review_vs_decisive_disagrees(self):
        """Leader partial->review, validator supported->accept: False."""
        leader = _leader_result("partial", "relevant", True)
        validator = _llm_response("supported", "relevant", True)
        self.assertFalse(self._validate(leader, validator))

    def test_supported_review_vs_partial_review_disagrees(self):
        """Leader supported+no-evidence->review, validator partial->review: False.

        Both derive `review`, but `supported` is not in the review class:
        the leader claims the evidence supports the requirement while the
        validator says it only partially does — a genuine disagreement
        about what the evidence says.
        """
        leader = _leader_result("supported", "relevant", False)
        validator = _llm_response("partial", "relevant", True)
        self.assertFalse(self._validate(leader, validator))

    # -- 4. Broken validator output disagrees --

    def test_validator_malformed_json(self):
        """Validator's own LLM returns malformed JSON: False."""
        leader = _leader_result("supported", "relevant", True)
        self.assertFalse(self._validate(leader, "not json at all {{{"))

    def test_validator_missing_field(self):
        """Validator's own LLM omits evidence_found: False."""
        leader = _leader_result("supported", "relevant", True)
        broken = {"evidence_assessment": "supported", "semantic_relevance": "relevant"}
        self.assertFalse(self._validate(leader, broken))

    def test_validator_invalid_enum(self):
        """Validator's own LLM returns an invalid assessment label: False."""
        leader = _leader_result("supported", "relevant", True)
        broken = _llm_response("definitely", "relevant", True)
        self.assertFalse(self._validate(leader, broken))

    # -- 5. Structural checks retained --

    def test_leader_decision_inconsistent_with_table(self):
        """Leader decision contradicts the table: False, no LLM call needed.

        The validator agrees semantically (its scripted response matches
        the leader's fields), but the leader's decision field is wrong —
        the deterministic shape check must reject it before any LLM call.
        """
        leader = _leader_result("supported", "relevant", True, decision="reject")
        validator = _llm_response("supported", "relevant", True)
        self.assertFalse(self._validate(leader, validator))
        self.assertEqual(stub.PROMPTS, [])

    def test_quote_exists_mismatch(self):
        """Leader quote_exists differs from compute()'s value: False."""
        leader = _leader_result("supported", "relevant", True, quote_exists=False)
        validator = _llm_response("supported", "relevant", True)
        self.assertFalse(self._validate(leader, validator, quote_exists=True))

    def test_leader_result_not_a_return(self):
        """Leader result not wrapped in gl.vm.Return: False."""
        leader = _leader_result("supported", "relevant", True)
        validator = _llm_response("supported", "relevant", True)
        stub.queue_responses([validator])
        self.assertFalse(
            _validator_fn(leader, REQUIREMENT, PROPOSAL, QUOTE, True)
        )

    def test_leader_supported_without_evidence_found(self):
        """Leader supported + evidence_found=False fails consistency: False."""
        leader = _leader_result("supported", "relevant", False)
        # Force the decision the table would give for these fields (review)
        # so the shape check passes and the cross-field rule is the decider.
        self.assertEqual(leader["decision"], "review")
        validator = _llm_response("supported", "relevant", False)
        self.assertFalse(self._validate(leader, validator))

    def test_leader_missing_quote_exists(self):
        """Leader result without quote_exists: False."""
        leader = _leader_result("supported", "relevant", True)
        del leader["quote_exists"]
        validator = _llm_response("supported", "relevant", True)
        self.assertFalse(self._validate(leader, validator))


class TestV5EndToEnd(unittest.TestCase):
    """Full compute() runs through the stubbed run_nondet_unsafe."""

    def setUp(self):
        stub.reset()
        self.contract = PEVContract()

    def _compute(self):
        return self.contract.compute("PROP-001", REQUIREMENT, PROPOSAL, QUOTE)

    def test_agreement_stores_evaluation(self):
        """Leader and validator agree: compute() stores and returns the result."""
        stub.queue_responses([
            _llm_response("supported", "relevant", True),
            _llm_response("supported", "relevant", True),
        ])
        result = self._compute()
        self.assertEqual(result["decision"], "accept")
        self.assertEqual(result["evidence_assessment"], "supported")
        self.assertTrue(result["quote_exists"])
        self.assertTrue(result["evaluation_complete"])
        self.assertFalse(result["review_required"])
        stored = self.contract.get_evaluation("PROP-001")
        self.assertEqual(stored, result)

    def test_leader_and_validator_prompts_identical(self):
        """Leader and validator run the SAME prompt byte-for-byte."""
        stub.queue_responses([
            _llm_response("supported", "relevant", True),
            _llm_response("supported", "relevant", True),
        ])
        self._compute()
        self.assertEqual(len(stub.PROMPTS), 2)
        self.assertEqual(stub.PROMPTS[0], stub.PROMPTS[1])

    def test_disagreement_stores_nothing(self):
        """Leader and validator disagree: compute() fails, nothing stored."""
        stub.queue_responses([
            _llm_response("supported", "relevant", True),
            _llm_response("contradicted", "relevant", True),
        ])
        with self.assertRaises(stub.vm.UserError):
            self._compute()
        self.assertIsNone(self.contract.get_evaluation("PROP-001"))

    def test_review_class_agreement_end_to_end(self):
        """Leader partial, validator insufficient: both review -> stored."""
        stub.queue_responses([
            _llm_response("partial", "relevant", True),
            _llm_response("insufficient", "relevant", True),
        ])
        result = self._compute()
        self.assertEqual(result["decision"], "review")
        self.assertTrue(result["review_required"])
        self.assertEqual(self.contract.get_evaluation("PROP-001"), result)

    def test_get_evaluation_unknown_id(self):
        """Unknown proposal_id returns None."""
        self.assertIsNone(self.contract.get_evaluation("NOPE"))


if __name__ == "__main__":
    unittest.main()
