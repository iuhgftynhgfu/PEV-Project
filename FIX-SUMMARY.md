# PEV V5 — Fix Summary (Resubmission)

## What was rejected

GenLayer Portal contribution "Procurement Evidence Verifier (PEV) —
Evidence-Based Procurement Evaluation on GenLayer", category Intelligent
Contracts, submission `41ff5825…`, rejected Oct 31, 2026. V4 contract
deployed at `0x886268ee1981395FC3b6e0A8c0821B89B1360fB1`.

Rejection reason (verbatim):

> "The validator checks output structure and internal consistency, but it
> does not independently evaluate the proposal evidence. Opposite
> assessments can therefore both pass and produce conflicting accept/reject
> decisions. Please redesign validation so validators independently bind
> the semantic assessment and resulting decision, then deploy and submit
> matching corrected source."

## The flaw, precisely

V4's `validator_fn` never looked at the proposal evidence. It checked the
leader result's shape, allowed enum values, decision-table consistency,
cross-field rules, and the deterministic `quote_exists` — and its own
comment said "Do not issue a second LLM call here." So a leader returning
`supported → accept` passed every check, and a leader returning
`contradicted → reject` for the SAME proposal also passed every check.
Consensus was over output shape, not over what the evidence says.

## What V5 changes

`contracts/pev_contract.py` (the only contract file; `Depends` header kept):

1. **Shared assessment prompt** — `_build_assessment_prompt()` (lines
   105–127) builds the prompt once, used byte-for-byte by the leader and
   every validator, so the validator re-runs the SAME task the leader ran.
2. **Shared parsing/validation** — `_parse_assessment()` (lines 130–153)
   parses and validates LLM output identically for leader and validator.
3. **Rewritten validator** — module-level `_validator_fn()` (lines 173–230),
   called from `compute()` through a thin closure so it is directly
   unit-testable. It keeps ALL V4 deterministic checks, then:
   - issues its OWN `gl.nondet.exec_prompt` call with the shared prompt;
   - derives its OWN decision from its own assessment via the same
     deterministic table;
   - accepts the leader's result ONLY if its own decision equals the
     leader's decision AND its own `evidence_assessment` is compatible
     with the leader's — identical, or both in the review class
     (`partial` / `insufficient` / `ambiguous`);
   - returns `False` on any failure, including malformed output from its
     own LLM call (disagree rather than agree on broken output).
4. **Review-class equivalence** — `_assessments_compatible()` (lines
   156–171): `partial`/`insufficient`/`ambiguous` all mean the same outcome
   (evidence does not establish the requirement; human review needed), so
   honest validators may differ on the label without disagreeing on the
   outcome. Requiring byte-identical labels would stall consensus on LLM
   wording variance. `explanation` free text is never compared.
5. **Unchanged** — deterministic input validation, 50,000-char limit,
   verbatim `quote_exists` check, decision table, stored result shape,
   `get_evaluation`, `evaluation_complete` / `review_required` flags.

**Why this answers the rejection:** a validator that independently assesses
`contradicted` derives `reject` and votes `False` against a leader claiming
`supported → accept`, and vice versa. Opposite assessments can no longer
both pass — each is rejected by every validator whose independent judgment
disagrees. Because the decision is a deterministic function of the full
assessment triple, decision equality already constrains `semantic_relevance`
and `evidence_found` (e.g. a leader `accept` requires relevant + true; a
validator whose own reading is `irrelevant` derives `reject` and votes
`False`).

**Cost note:** every validator now makes its own LLM call per `compute()`.
That is the intended GenLayer comparative model (5 validators, 5 independent
assessments) and is what makes the vote carry judgment.

## Tests

`tests/genlayer_stub.py` (new) — stdlib-only stub of the `genlayer` package
(no-op decorators, plain-dict storage, `UserError`/`Return`, scripted
`exec_prompt` with prompt recording, `run_nondet_unsafe` that raises on a
validator `False`, modelling "no consensus, no state modified"). Needed
because the `genlayer` package on PyPI is an intentionally empty placeholder
and `gltest` is not published on PyPI; the real SDK only exists inside
GenLayer Studio.

`tests/test_pev_v5_validator.py` (new) — 22 tests, all passing:
- Opposite assessments must NOT both pass (both directions).
- Agreement passes (accept, reject, reject-irrelevant).
- Review-class equivalence (partial vs insufficient, insufficient vs
  ambiguous pass; review vs decisive fails; `supported`+no-evidence vs
  `partial` fails even though both derive `review`).
- Broken validator output disagrees (malformed JSON, missing field,
  invalid enum).
- Structural checks retained (decision-table inconsistency — with no LLM
  call issued; `quote_exists` mismatch; non-`Return` leader result;
  `supported` without `evidence_found`; missing `quote_exists`).
- End-to-end via stubbed `run_nondet_unsafe`: agreement stores the
  evaluation; leader and validator prompts are byte-identical;
  disagreement stores nothing; review-class agreement stores a `review`.

`tests/test_pev_direct.py` (fixed) — the 4 decision-table tests called
`contract._compute_decision(...)`, but `_compute_decision` is a module-level
function, not a method (latent V4 bug: `AttributeError` even with `genlayer`
installed). They now import the module-level helper directly and pass.

**Full suite: 32 tests, 32 passed, 0 failed, 0 errors**
(`python -m unittest tests.test_pev_direct tests.test_pev_v5_validator`,
Python 3.12.3, 2026-11-21). Full per-test table in README "Testing Results".

Docs updated: README (§3, §4, §5, Equivalence Principle, architecture
diagram with V5 line numbers, Testing Results, Test Status Summary,
Limitations) and `docs/manual_studio_test_plan.md` (new V5 Studio cases
M14–M16 + V5 retest note for M01–M08/M12–M13).

## What could NOT be verified locally

- **Live-network validator behavior** — the documented outcome of a
  majority-`False` verdict (leader rotation / retry, then undetermined
  with no state modified) is per GenLayer's Equivalence Principle docs;
  only a live V5 deployment can confirm it empirically. The local stub
  models it as a failed `compute()` with nothing stored.
- **Studio simulator** — cannot be installed locally (no `gltest` on PyPI;
  PyPI `genlayer` is an empty placeholder). Studio is used hosted at
  studio.genlayer.com.
- **Real-LLM agreement rates** — the stub scripts LLM responses; how often
  independent validators agree on real proposals (especially near the
  review boundary) can only be measured on the live deployment.

## Deploy + resubmit (user steps)

1. **Push V5 to GitHub** — commit the V5 contract, updated docs/tests, and
   this file; push to `iuhgftynhgfu/PEV-Project` (main branch). No GitHub
   auth exists on the build VM, so this step runs from the user's own
   browser/machine.
2. **Deploy V5 in GenLayer Studio** — open studio.genlayer.com, upload the
   V5 contract file (Add From File), open Run and Debug, check constructor
   inputs (none), click Deploy, select the GenLayer testnet environment,
   confirm in the wallet. Copy the NEW contract address from the
   Deployments panel. Funding: Studio's faucet button funds the Studio
   browser account with test GEN.
   (Docs: https://docs.genlayer.com/developers/decentralized-applications/dapp-development-workflow)
3. **Smoke-test the new deployment** — call `compute()` on 2–3 cases from
   the Studio test plan (one clear accept, one clear reject, one review)
   and confirm FINALIZED / MAJORITY_AGREE and a matching `get_evaluation`
   result. If possible, run M14 and check the validator panel for an
   independent `False` verdict on disagreement.
4. **Resubmit on the GenLayer Portal** — open the rejected contribution,
   click **Resubmit** (creates a new editable contribution; the rejected
   one stays unchanged), update the contract address to the NEW V5
   deployment, point the source at the updated GitHub repo state, and
   describe the fix: validators now independently re-evaluate the proposal
   evidence with their own LLM call and consensus is over the bound
   (assessment, decision) pair, so opposite assessments can no longer both
   pass. Category (Intelligent Contracts) is still OPEN with no deadline.
5. **Do NOT reuse the V4 address (`0x8862…0fB1`) or V4 source** — the
   rejection explicitly requires "deploy and submit matching corrected
   source": the deployed bytecode and the submitted source must both be V5.
