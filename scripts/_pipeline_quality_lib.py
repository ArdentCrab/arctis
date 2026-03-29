"""
Shared helpers for pipeline quality / variance tooling (scripts only).

Uses stdlib only — no extra pip dependencies.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import httpx
from arctis.control_plane.pipelines import bind_ir_to_payload, register_modules_for_ir
from arctis.engine import Engine, TenantContext
from arctis.pipeline_a import build_pipeline_a_ir
from arctis.pipeline_a.prompt_binding import bind_pipeline_a_prompt
from arctis.policy.memory_db import in_memory_policy_session
from arctis.policy.resolver import resolve_effective_policy

REPO_ROOT = Path(__file__).resolve().parents[1]


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, default=str, ensure_ascii=False)


def extract_text_blob(obj: Any, *, max_chars: int = 50_000) -> str:
    """Flatten JSON-like structures into a single normalized string for similarity."""
    parts: list[str] = []

    def walk(x: Any) -> None:
        if len("".join(parts)) >= max_chars:
            return
        if isinstance(x, str):
            parts.append(x)
        elif isinstance(x, dict):
            for k in sorted(x.keys()):
                walk(k)
                walk(x[k])
        elif isinstance(x, list):
            for i in x:
                walk(i)
        elif x is not None:
            parts.append(str(x))

    walk(obj)
    raw = " ".join(parts)
    raw = re.sub(r"\s+", " ", raw).strip().lower()
    return raw[:max_chars]


def token_jaccard(a: str, b: str) -> float:
    ta = {w for w in re.findall(r"[a-z0-9_]+", a) if len(w) > 1}
    tb = {w for w in re.findall(r"[a-z0-9_]+", b) if len(w) > 1}
    if not ta and not tb:
        return 1.0
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    union = len(ta | tb)
    return inter / union if union else 0.0


def blended_text_similarity(reference: str, candidate: str) -> float:
    """Proxy for semantic similarity without embeddings (deterministic)."""
    if not reference.strip():
        return 1.0
    r = reference.strip().lower()
    c = candidate.strip().lower()
    seq = SequenceMatcher(a=r, b=c).ratio()
    jac = token_jaccard(r, c)
    return max(0.0, min(1.0, 0.45 * seq + 0.55 * jac))


def get_json_path(obj: Any, dotted: str) -> Any:
    cur: Any = obj
    for part in dotted.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def match_expect_value(actual: Any, spec: str) -> bool:
    if spec.startswith("regex:"):
        pat = spec[6:]
        return bool(re.search(pat, str(actual), flags=re.DOTALL))
    if spec.startswith("prefix:"):
        return str(actual).startswith(spec[7:])
    if spec.startswith("contains:"):
        return spec[9:] in str(actual)
    return str(actual) == spec


@dataclass
class ExpectBlock:
    status: str = "success"
    reference_text: str = ""
    required_output_keys: list[str] = field(default_factory=list)
    required_phrases: list[str] = field(default_factory=list)
    forbidden_substrings: list[str] = field(default_factory=list)
    json_paths: dict[str, str] = field(default_factory=dict)
    min_effects: int = 0
    min_semantic_score: float = 0.0
    min_structural_score: float = 0.0
    min_factual_score: float = 0.0

    @staticmethod
    def from_dict(d: dict[str, Any]) -> ExpectBlock:
        return ExpectBlock(
            status=str(d.get("status", "success")),
            reference_text=str(d.get("reference_text", "")),
            required_output_keys=list(d.get("required_output_keys", [])),
            required_phrases=list(d.get("required_phrases", [])),
            forbidden_substrings=list(d.get("forbidden_substrings", [])),
            json_paths={str(k): str(v) for k, v in dict(d.get("json_paths", {})).items()},
            min_effects=int(d.get("min_effects", 0)),
            min_semantic_score=float(d.get("min_semantic_score", 0.0)),
            min_structural_score=float(d.get("min_structural_score", 0.0)),
            min_factual_score=float(d.get("min_factual_score", 0.0)),
        )


def score_structural(
    output: dict[str, Any] | None,
    exp: ExpectBlock,
    *,
    effects: list[Any] | None = None,
) -> tuple[float, list[str]]:
    notes: list[str] = []
    if output is None:
        return 0.0, ["output is null"]
    weights = 0
    acc = 0.0
    if exp.required_output_keys:
        weights += 1
        ok = all(k in output for k in exp.required_output_keys)
        if ok:
            acc += 1.0
        else:
            missing = [k for k in exp.required_output_keys if k not in output]
            notes.append(f"missing keys: {missing}")
    if exp.json_paths:
        weights += 1
        good = 0
        total = len(exp.json_paths)
        for path, want in exp.json_paths.items():
            got = get_json_path(output, path)
            if match_expect_value(got, want):
                good += 1
            else:
                notes.append(f"path {path!r}: want {want!r}, got {got!r}")
        acc += good / total if total else 1.0
    if exp.min_effects > 0:
        weights += 1
        nfx = len(effects) if isinstance(effects, list) else 0
        if nfx >= exp.min_effects:
            acc += 1.0
        else:
            notes.append(f"effects count {nfx} < min_effects {exp.min_effects}")
    if weights == 0:
        return 1.0, notes
    return acc / weights, notes


def score_factual(output: dict[str, Any] | None, exp: ExpectBlock) -> tuple[float, list[str]]:
    notes: list[str] = []
    blob = extract_text_blob(output) if output else ""
    if exp.required_phrases:
        hit = sum(1 for p in exp.required_phrases if p.lower() in blob)
        frac = hit / len(exp.required_phrases)
        if frac < 1.0:
            notes.append(f"phrases matched {hit}/{len(exp.required_phrases)}")
    else:
        frac = 1.0
    forbid_hits = [fs for fs in exp.forbidden_substrings if fs and fs.lower() in blob]
    if forbid_hits:
        notes.append(f"forbidden substrings present: {forbid_hits}")
        return 0.0, notes
    return frac, notes


def score_semantic(output: dict[str, Any] | None, exp: ExpectBlock) -> tuple[float, list[str]]:
    if not exp.reference_text.strip():
        return 1.0, []
    cand = extract_text_blob(output)
    sim = blended_text_similarity(exp.reference_text, cand)
    notes = (
        []
        if sim >= exp.min_semantic_score
        else [f"semantic proxy {sim:.3f} < {exp.min_semantic_score}"]
    )
    return sim, notes


def run_local_pipeline_a(
    input_payload: dict[str, Any],
    *,
    tenant_id: str = "quality_eval",
    data_residency: str = "US",
    dry_run: bool = False,
) -> dict[str, Any]:
    """Execute Pipeline A in-process (same binding path as control plane)."""
    engine = Engine()
    pdb = in_memory_policy_session()
    tenant = TenantContext(
        tenant_id=tenant_id,
        data_residency=data_residency,
        budget_limit=None,
        resource_limits={"cpu": 10000, "memory": 1024, "max_wall_time_ms": 30_000},
        dry_run=dry_run,
    )
    ir = build_pipeline_a_ir()
    pol = resolve_effective_policy(pdb, tenant_id, ir.name)
    tenant.policy = pol
    bound = bind_pipeline_a_prompt(
        ir,
        input_payload,
        tenant_id=tenant_id,
        effective_policy=pol,
        policy_db=pdb,
    )
    ir = bind_ir_to_payload(bound.ir, input_payload)
    register_modules_for_ir(engine, ir)
    engine.ai_region = data_residency
    try:
        result = engine.run(
            ir,
            tenant,
            run_payload=input_payload,
            policy_db=pdb,
            enforcement_prefix_snapshot=bound.enforcement_prefix_snapshot,
            review_db=pdb,
        )
    except Exception as e:
        return {
            "status": "error",
            "error_type": type(e).__name__,
            "error_message": str(e),
            "output": None,
            "effects": [],
            "execution_trace": None,
        }
    fx = getattr(result, "effects", None)
    effects_list = list(fx) if isinstance(fx, list) else []
    trace = getattr(result, "execution_trace", None)
    if trace is not None and not isinstance(trace, list):
        try:
            trace = list(trace)
        except TypeError:
            trace = None
    out_obj = result.output if isinstance(result.output, dict) else {}
    return {
        "status": "success",
        "output": out_obj,
        "effects": effects_list,
        "execution_trace": trace,
        "engine_version": getattr(result, "engine_version", None),
        "cost": getattr(result, "cost", None),
        "step_costs": getattr(result, "step_costs", None),
    }


def run_http_pipeline(
    base_url: str,
    api_key: str,
    pipeline_id: str,
    input_payload: dict[str, Any],
    *,
    timeout_s: float = 120.0,
) -> dict[str, Any]:
    base = base_url.rstrip("/") + "/"
    path = f"pipelines/{pipeline_id}/run"
    with httpx.Client(base_url=base, headers={"X-API-Key": api_key}, timeout=timeout_s) as client:
        r = client.post(path, json={"input": dict(input_payload)})
        try:
            body = r.json()
        except Exception:
            body = {"raw": r.text}
        if r.status_code >= 400:
            return {
                "status": "error",
                "http_status": r.status_code,
                "error_body": body,
                "output": None,
                "effects": [],
                "execution_trace": None,
            }
        eff = body.get("effects")
        return {
            "status": str(body.get("status", "error")),
            "output": body.get("output") if isinstance(body.get("output"), dict) else None,
            "effects": list(eff) if isinstance(eff, list) else [],
            "execution_trace": body.get("execution_trace"),
            "engine_version": body.get("engine_version"),
            "cost": body.get("cost"),
            "step_costs": body.get("step_costs"),
            "run_id": str(body.get("run_id")) if body.get("run_id") else None,
        }


def load_matrix(path: Path) -> dict[str, Any]:
    data = load_json(path)
    if not isinstance(data, dict):
        msg = "matrix root must be an object"
        raise ValueError(msg)
    return data


def matrix_cases(data: dict[str, Any]) -> list[dict[str, Any]]:
    cases = data.get("cases")
    if not isinstance(cases, list) or not cases:
        msg = "matrix.cases must be a non-empty list"
        raise ValueError(msg)
    return cases


def parse_uuid(s: str) -> uuid.UUID:
    return uuid.UUID(str(s).strip())


def ensure_reports_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
