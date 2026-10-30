# Procurement Evidence Verifier (PEV)

An Intelligent Contract for GenLayer that evaluates whether a vendor proposal contains textual evidence supporting procurement specification requirements.

## Project Overview

PEV (Procurement Evidence Verifier) is a GenLayer Intelligent Contract prototype designed to evaluate procurement proposals against specification requirements. The contract determines whether submitted textual evidence in a proposal supports, partially supports, contradicts, or fails to establish each requirement.

## Problem Statement

Procurement teams manually review vendor proposals to verify compliance with specification requirements. This process is time-consuming and prone to human inconsistency. PEV automates the evidence evaluation step, providing a structured, deterministic decision output based on LLM-assisted semantic evaluation and on-chain storage of results.

## Why PEV Matters

- **Deterministic decision logic**: The final decision (accept / reject / review) is computed deterministically inside the contract from the LLM-evaluated evidence fields, not by the LLM directly.
- **Deterministic quote verification**: The contract checks whether a candidate quote exists verbatim in the proposal text, independent of LLM output.
- **On-chain storage**: Evaluation results are stored in contract state as JSON-serialized records, keyed by proposal ID.
- **No compliance claims**: The contract records evidence characteristics only; it does not certify real-world compliance, legal validity, or security.

## Architecture

```
PEV Contract
├── compute() - Main entry point (write)
│   ├── Input validation (proposal_id, requirement, proposal, candidate_quote)
    ├── quote_exists: Deterministic substring check (computed outside LLM)
    ├── leader_fn: LLM-based semantic evaluation via gl.nondet.exec_prompt
    ├── validator_fn: Independent structural validation of leader output
    ├── run_nondet_unsafe: Non-deterministic execution wrapper
    └── State storage: JSON-serialized results in TreeMap[str, str]
└── get_evaluation() - Read-only access (view)
```

### Contract State

| Field | Type | Description |
|-------|------|-------------|
| `evaluations` | `TreeMap[str, str]` | Persistent storage mapping proposal_id to JSON-serialized result |

### Contract Methods

| Method | Decorator | Parameters | Returns |
|--------|-----------|------------|---------|
| `compute` | `@gl.public.write` | `proposal_id`, `requirement`, `proposal`, `candidate_quote` | `dict` with evaluation result |
| `get_evaluation` | `@gl.public.view` | `proposal_id` | `dict` or `None` |

## How It Works

### 1. Input Validation

All inputs (`proposal_id`, `requirement`, `proposal`, `candidate_quote`) are validated as strings where required. `proposal_id` and `requirement` must be non-empty. `candidate_quote` may be empty.

### 2. Deterministic Quote Check (`quote_exists`)

The contract checks whether `candidate_quote` appears as a literal substring in `proposal`. This check is:
- **Deterministic**: Same inputs always produce the same result
- **Independent**: Computed outside the LLM prompt
- **Non-conclusive**: `quote_exists=False` does not mean no other evidence exists in the proposal

### 3. Leader Function (Semantic Evaluation)

The leader executes `gl.nondet.exec_prompt()` with a structured prompt that:
- Presents the requirement and proposal as untrusted data
- Explicitly instructs the LLM to ignore any instructions embedded in the proposal
- Requests JSON output with: `evidence_assessment`, `semantic_relevance`, `evidence_found`, `explanation`
- Explicitly states: "Do not return a decision field; the contract derives it deterministically"

### 4. Validator Function (Independent Verification)

The validator:
1. Receives `leader_result` as `gl.vm.Return` and extracts `.calldata`
2. Validates the leader's output structure and values
3. Checks internal consistency (decision matches decision table)
4. Verifies `quote_exists` against the deterministic value computed in `compute()`
5. Does **not** re-call `leader_fn()` (avoids non-deterministic LLM variance)

### 5. Consensus and Finalization

`gl.vm.run_nondet_unsafe(leader_fn, validator_fn)` executes the leader and validator. The result is validated, stored as JSON in `TreeMap[str, str]`, and returned.

## Decision Logic

The contract uses a deterministic decision table computed inside the contract (not by the LLM):

| evidence_assessment | semantic_relevance | evidence_found | decision |
|---------------------|-------------------|----------------|----------|
| supported | relevant | true | **accept** |
| contradicted | any | any | **reject** |
| any | irrelevant | any | **reject** |
| supported | relevant | false | **review** |
| partial | any | any | **review** |
| insufficient | any | any | **review** |
| ambiguous | any | any | **review** |

The `decision` field is computed locally by the contract, not returned by the LLM. This prevents LLM output variance from affecting the final verdict.

## Evidence Assessment

| Status | Meaning |
|--------|---------|
| `supported` | Evidence clearly satisfies the requirement |
| `partial` | Evidence addresses part of the requirement |
| `contradicted` | Evidence directly contradicts the requirement |
| `insufficient` | Evidence relevant but doesn't establish the requirement |
| `ambiguous` | Requirement or evidence too ambiguous to judge |

## Equivalence Principle

GenLayer's equivalence principle requires that all validators produce identical outputs for the same inputs. PEV is designed so that:

1. **Deterministic fields**: `quote_exists`, `input_within_limit`, `evaluation_complete`, `review_required` are computed deterministically inside `compute()`.
2. **LLM outputs are not compared textually**: `evidence_assessment`, `semantic_relevance`, `evidence_found`, `decision`, `explanation` are evaluated by the LLM but validated for structure and internal consistency, not for exact textual match across validators.
3. **Decision derived locally**: The `decision` field is computed from the other fields using a deterministic table.

## Testing Results

### Executed Tests (Phase 9 — Phase 9 Isolated Deterministic Tests)

6 independent deterministic tests were successfully executed without the GenLayer runtime:

| # | Test | Result |
|---|------|--------|
| 1 | `test_quote_exists_true` | PASS |
| 2 | `test_quote_exists_false` | PASS |
| 3 | `test_empty_quote` | PASS |
| 4 | `test_input_within_limit` | PASS |
| 5 | `test_evaluation_complete_from_fields` | PASS |
| 6 | `test_evaluation_complete_missing_field` | PASS |

**Total**: 6 executed | **6 passed** | **0 failed**

### Tests Not Executed (Require GenLayer Runtime)

4 deterministic logic tests were identified but **not executed** because they require importing `PEVContract` from `contracts.pev_contract.py`, which depends on the `genlayer` package that is not available in this environment:

- `test_compute_decision_accept`
- `test_compute_decision_reject_contradicted`
- `test_compute_decision_reject_irrelevant`
- `test_compute_decision_review`

### Manual Studio Test Plan (Not Executed)

The following 13 test cases are documented in `docs/manual_studio_test_plan.md` and require a running GenLayer Studio environment with validator nodes:

| # | Test Case | Expected Outcome |
|---|-----------|------------------|
| 1 | ACCEPT — Direct supporting evidence | `evidence_assessment="supported"`, `decision="accept"` |
| 2 | REJECT — Contradictory evidence | `evidence_assessment="contradicted"`, `decision="reject"` |
| 3 | REVIEW — Partial support | `evidence_assessment="partial"`, `decision="review"` |
| 4 | Fabricated quote | `quote_exists=False` |
| 5 | Quote from unrelated section | `quote_exists=True`, `evidence_assessment="insufficient"` |
| 6 | Prompt injection — false positive | `quote_exists=True`, `evidence_assessment` based on LLM eval |
| 7 | Prompt injection — fabricated quote | `quote_exists=False` (not in proposal text) |
| 8 | Conflicting evidence | `quote_exists=True`, `evidence_assessment` based on LLM eval |
| 9 | Malformed LLM response | `gl.vm.UserError` raised |
| 10 | Missing required fields | `gl.vm.UserError` raised |
| 11 | Validator disagreement | Consensus failure if validators disagree |
| 12 | Oversized proposal | `gl.vm.UserError("proposal exceeds maximum length")` |
| 13 | Ambiguous requirement | `evidence_assessment="ambiguous"`, `decision="review"` |

### Test Status Summary

| Category | Count | Status |
|----------|-------|--------|
| Executed (Phase 9) | 6 | All passed |
| Not executed (require GenLayer runtime) | 4 | Pending `genlayer` package availability |
| Manual Studio Test Plan | 13 | Pending GenLayer Studio environment |

**Test framework**: `genlayer-test` (Direct Mode) — not verified as available in this environment

## Installation and Usage

### Prerequisites

- Python 3.14+
- GenLayer SDK (`genlayer` package) — availability for Python 3.14.6 on Android Termux not verified
- `gltest` CLI tool — availability not verified

### Installation

Dependencies are not pinned in `requirements.txt` because the GenLayer SDK (`genlayer`) and testing tool (`gltest`) have not been verified for availability or compatibility with Python 3.14.6 on this environment. Refer to official GenLayer documentation for installation instructions.

### Contract Deployment

Deployment commands are not documented here because the official GenLayer deployment procedure has not been verified in this environment. Refer to official GenLayer documentation.

### Contract Invocation

```python
from contracts.pev_contract import PEVContract

contract = PEVContract()
result = contract.compute(
    proposal_id="PROP-001",
    requirement="System shall use AES-256 encryption at rest",
    proposal="We implement AES-256 encryption for data at rest.",
    candidate_quote="AES-256 encryption at rest"
)
print(result)
```

### Retrieving an Evaluation

```python
result = contract.get_evaluation("PROP-001")
print(result)
```

## Limitations

1. **GenLayer SDK dependency**: The `genlayer` package has not been verified as available for Python 3.14.6 on Android Termux.
2. **Android Termux compatibility**: Not verified for ARM architecture.
3. **No formal security audit**: This contract has not undergone professional security review.
4. **Single requirement per evaluation**: Each `compute()` call evaluates one requirement against one proposal.
5. **No batch evaluation**: Multiple requirements require multiple contract calls.
6. **LLM-based semantic evaluation**: The `evidence_assessment`, `semantic_relevance`, and `evidence_found` fields are produced by an LLM and may vary between executions; they are validated for structure and consistency but not for factual correctness.

## License

The license for this project has not been determined. No LICENSE file is included.

---

**Important**: This contract evaluates textual evidence only. It does not certify real-world compliance, legal validity, or security of vendor proposals. All evaluations are subject to GenLayer's equivalence principle and should be reviewed by human reviewers for final decisions.