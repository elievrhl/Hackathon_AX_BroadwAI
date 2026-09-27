from types import SimpleNamespace

import pytest

from broadwai.llm import BudgetExceeded
from scripts.evaluation_spend import SpendGuard


def test_guard_reserves_concurrent_calls_and_persists_unknown_usage(tmp_path):
    path = tmp_path / "spend.json"
    guard = SpendGuard(path, limit=0.15)
    kwargs = {"model": "gpt-5.4-mini", "max_output_tokens": 6000, "input": "test"}
    first = guard.reserve(kwargs)
    guard.reserve(kwargs)
    guard.reserve(kwargs)
    with pytest.raises(BudgetExceeded):
        guard.reserve(kwargs)
    guard.settle(first, SimpleNamespace(usage=SimpleNamespace(input_tokens=100, output_tokens=20)))
    guard.reserve(kwargs)
    held = guard.held
    guard.close()
    reopened = SpendGuard(path, limit=0.15)
    assert reopened.held == held
    reopened.close()


async def test_guard_blocks_before_the_provider_and_keeps_failed_reservation(tmp_path):
    guard = SpendGuard(tmp_path / "spend.json", limit=0.1)
    calls = []

    async def provider(**kwargs):
        calls.append(kwargs)
        raise TimeoutError

    call = guard.wrap(provider)
    with pytest.raises(BudgetExceeded):
        await call(model="unpriced", max_output_tokens=200)
    assert not calls
    with pytest.raises(TimeoutError):
        await call(model="gpt-5.4-nano", max_output_tokens=200)
    assert guard.held > 0 and calls[0]["service_tier"] == "default"
    assert guard.data["calls"][0]["status"] == "unknown_charge"
    guard.close()
