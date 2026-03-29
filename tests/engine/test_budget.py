"""Unit tests for E2 budget helpers."""

from __future__ import annotations

import pytest

from arctis.engine.budget import BudgetExceeded, check_run_budget, estimate_tokens


def test_estimate_tokens_deterministic() -> None:
    assert estimate_tokens(None) == 0
    a = estimate_tokens({"z": 1, "a": 2})
    b = estimate_tokens({"a": 2, "z": 1})
    assert a == b
    assert a > 0


def test_check_run_budget_respects_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    from arctis.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("ARCTIS_BUDGET_MAX_TOKENS_PER_RUN", "10")
    get_settings.cache_clear()
    check_run_budget(10)
    with pytest.raises(BudgetExceeded) as ei:
        check_run_budget(11)
    assert ei.value.code == "run_token_limit"
    get_settings.cache_clear()
