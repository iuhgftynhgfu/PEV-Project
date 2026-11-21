"""Stdlib-only stub of the `genlayer` package for local testing.

Injects a fake `genlayer` module into sys.modules so contracts/pev_contract.py
can be imported and exercised in plain local Python, without the GenLayer SDK,
runtime, or any LLM call.

What the stub provides:
- gl.Contract: base class whose instances get a plain-dict `evaluations`
  store (mirrors TreeMap[str, str] closely enough for local tests).
- gl.public.write / gl.public.view: no-op decorators.
- gl.vm.UserError: exception type.
- gl.vm.Return: wrapper with a `.calldata` attribute, as the real runtime
  passes leader results to validators.
- gl.nondet.exec_prompt: scripted — returns queued responses in order and
  records every prompt issued, so tests can assert the leader and the
  validator ran the SAME prompt.
- gl.vm.run_nondet_unsafe(leader_fn, validator_fn): runs the leader, wraps
  its result in a Return, runs the validator against it. If the validator
  returns True the leader's dict is returned; if False it raises
  gl.vm.UserError, modelling "no consensus reached, no state modified"
  (the real runtime rotates the leader and retries; if consensus still
  cannot be reached the transaction goes undetermined and no state is
  modified — the observable local outcome is the same: nothing stored).

Usage (must run BEFORE importing the contract):
    import genlayer_stub
    genlayer_stub.install()
    genlayer_stub.queue_responses([leader_response, validator_response])
    from contracts.pev_contract import PEVContract

The stub is test tooling only. It is NOT part of the deployed contract and
must not be submitted as contract source.
"""

import sys
import types

RESPONSES = []
PROMPTS = []


def queue_responses(responses):
    """Queue scripted exec_prompt responses, served in order."""
    RESPONSES.extend(responses)


def reset():
    """Clear queued responses and recorded prompts (call in setUp)."""
    RESPONSES.clear()
    PROMPTS.clear()


class UserError(Exception):
    """Stand-in for gl.vm.UserError."""


class Return:
    """Stand-in for gl.vm.Return: carries the leader result in .calldata."""

    def __init__(self, calldata):
        self.calldata = calldata


class TreeMap(dict):
    """Stand-in for the contract's TreeMap[str, str] annotation."""

    def __class_getitem__(cls, item):
        return cls


class Contract:
    """Stand-in for gl.Contract: plain-dict storage for local tests."""

    def __new__(cls, *args, **kwargs):
        inst = super().__new__(cls)
        inst.evaluations = {}
        return inst


def _identity_decorator(fn):
    return fn


def _exec_prompt(prompt, response_format=None):
    PROMPTS.append(prompt)
    if not RESPONSES:
        raise RuntimeError("genlayer_stub: no scripted exec_prompt response left")
    return RESPONSES.pop(0)


def _run_nondet_unsafe(leader_fn, validator_fn):
    leader_result = leader_fn()
    verdict = validator_fn(Return(leader_result))
    if verdict is True:
        return leader_result
    raise UserError("validator rejected leader result (no consensus)")


public = types.SimpleNamespace(write=_identity_decorator, view=_identity_decorator)
vm = types.SimpleNamespace(
    UserError=UserError, Return=Return, run_nondet_unsafe=_run_nondet_unsafe
)
nondet = types.SimpleNamespace(exec_prompt=_exec_prompt)
gl = types.SimpleNamespace(Contract=Contract, public=public, vm=vm, nondet=nondet)

__all__ = ["gl", "TreeMap"]
_PEV_STUB = True


def install():
    """Install this module as `genlayer` in sys.modules.

    Idempotent: if the stub is already installed, returns the installed
    module. Returns the installed module object; use it to reach the
    scripted-response queue (queue_responses / reset / PROMPTS).
    """
    existing = sys.modules.get("genlayer")
    if existing is not None and getattr(existing, "_PEV_STUB", False):
        return existing
    sys.modules["genlayer"] = sys.modules[__name__]
    return sys.modules[__name__]
