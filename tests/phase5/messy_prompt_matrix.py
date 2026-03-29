"""
Phase 5 — Prompt Matrix helpers for messy Pipeline A inputs.

``PROMPT_A`` / ``PROMPT_B`` are the meta-prompts you would give an LLM to synthesize
messy user payloads. The matrix “comparison” uses a small deterministic rubric on
hand-authored sample batches (structure / diversity / noise), then the winning style
produces the 10 execution scenarios (no external LLM required for CI).
"""

from __future__ import annotations

import json
import re
import unicodedata
from typing import Any

# Meta-prompt A: conservative messy inputs (typos, mild whitespace).
PROMPT_A = """You generate JSON workflow inputs for system testing.
Each object must include string fields "prompt" and "idempotency_key" suitable for Pipeline A.
Use mild typos, extra spaces, and 1–2 redundant harmless keys (e.g. "note").
Do not include the substrings: password, secret, api_key, token, user_token (keys or values).
Keep prompts under 200 characters."""

# Meta-prompt B: richer messy inputs (unicode, formatting chaos, ambiguous casing).
PROMPT_B = """You generate JSON workflow inputs for adversarial sanitization testing.
Each object must include "prompt" and "idempotency_key".
Add unicode punctuation, mixed newlines/tabs, zero-width spaces, duplicated keys intent (normalized away),
and plausible metadata keys like "source" or "priority" with noisy string values.
Never use forbidden credential-like substrings (password, secret, api_key, token, user_token).
Vary length and structure across samples."""


def _batch_style_a() -> list[dict[str, Any]]:
    return [
        {
            "idempotency_key": "  phase5-a-1  ",
            "prompt": "  approve  this\trequest  please  ",
            "note": "extra",
        },
        {
            "idempotency_key": "a-2-typo",
            "prompt": "Plz route to aprove path quickly.",
        },
        {
            "idempotency_key": "a-3",
            "prompt": "NEEDS\nREVIEW\n(benign)",
            "meta": "low",
        },
        {
            "idempotency_key": "a-4",
            "prompt": "short",
        },
        {
            "idempotency_key": "a-5",
            "prompt": "Trailing spaces below\n",
            "x": 1,
        },
    ]


def _batch_style_b() -> list[dict[str, Any]]:
    zw = "\u200b"
    return [
        {
            "idempotency_key": f"b-1-{zw}key",
            "prompt": f"Résumé{zw}: envoyez vers approbation — version française.",
            "source": "email",
            "priority": " P2 ",
        },
        {
            "idempotency_key": "b-2-mixed",
            "prompt": "Line1\r\nLine2\tTabbed\rUnicode: 你好",
        },
        {
            "idempotency_key": "b-3",
            "prompt": unicodedata.normalize("NFKD", "café résumé naïve"),
        },
        {
            "idempotency_key": "b-4",
            "prompt": '{"fake":"json","in":"string"} but not our protocol',
        },
        {
            "idempotency_key": "b-5",
            "prompt": "MANUAL_REVIEW" + " " * 40 + "keyword noise",
        },
    ]


def _diversity_score(samples: list[dict[str, Any]]) -> float:
    prompts = [json.dumps(s.get("prompt", ""), sort_keys=True) for s in samples]
    return float(len(set(prompts)))


def _noise_score(samples: list[dict[str, Any]]) -> float:
    score = 0.0
    for s in samples:
        p = str(s.get("prompt", ""))
        if re.search(r"[^\x00-\x7f]", p):
            score += 2.0
        if re.search(r"[\r\t\u200b]", p):
            score += 1.5
        score += min(len(s.keys()), 6) * 0.2
        score += min(len(p), 400) / 200.0
    return score


def score_prompt_style(style: str) -> tuple[float, list[dict[str, Any]]]:
    batch = _batch_style_a() if style == "A" else _batch_style_b()
    total = _diversity_score(batch) * 1.5 + _noise_score(batch)
    return total, batch


def select_winning_prompt() -> tuple[str, float, float]:
    sa, _ = score_prompt_style("A")
    sb, _ = score_prompt_style("B")
    if sb >= sa:
        return "B", sa, sb
    return "A", sa, sb


def ten_scenarios_from_winner(winner: str) -> list[dict[str, Any]]:
    """Ten distinct runnable payloads (winner style dominates)."""
    a = _batch_style_a()
    b = _batch_style_b()
    pool = (b + a) if winner == "B" else (a + b)
    out: list[dict[str, Any]] = []
    for i, base in enumerate(pool[:10]):
        row = dict(base)
        row["idempotency_key"] = f"phase5-s{i}-{row.get('idempotency_key', 'x')}".strip()[:120]
        out.append(row)
    while len(out) < 10:
        out.append(
            {
                "idempotency_key": f"phase5-fill-{len(out)}",
                "prompt": f"fallback prompt {len(out)}",
            }
        )
    return out[:10]
