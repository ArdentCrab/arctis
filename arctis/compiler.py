"""Compiler entry points: Phase 3.1 parser; later phases stubbed."""

from __future__ import annotations

import copy
from collections import deque
from dataclasses import dataclass, field
from typing import Any


@dataclass
class StepAST:
    name: str
    type: str
    config: dict[str, Any] = field(default_factory=dict)
    next: str | None = None


@dataclass
class PipelineAST:
    name: str
    steps: list[StepAST]


@dataclass
class IRNode:
    name: str
    type: str
    config: dict[str, Any]
    next: list[str] = field(default_factory=list)


@dataclass
class IRPipeline:
    name: str
    nodes: dict[str, IRNode] = field(default_factory=dict)
    entrypoints: list[str] = field(default_factory=list)


def parse_pipeline(pipeline_definition: str | dict[str, Any]) -> PipelineAST:
    """
    Parse a minimal pipeline definition into an AST.

    Accepts:
      - dict with keys ``name`` (str) and ``steps`` (list of step mappings)
      - a non-empty single-line pipeline name string (no DSL / braces)

    Raises:
      TypeError: if the value is neither str nor dict.
      ValueError: if the structure is malformed (syntax only; no semantic checks).
    """
    if isinstance(pipeline_definition, dict):
        return _parse_pipeline_from_dict(pipeline_definition)
    if isinstance(pipeline_definition, str):
        return _parse_pipeline_from_string(pipeline_definition)
    raise TypeError("pipeline_definition must be str or dict")


def _parse_pipeline_from_dict(data: dict[str, Any]) -> PipelineAST:
    if "name" not in data:
        raise ValueError('pipeline dict requires key "name"')
    if "steps" not in data:
        raise ValueError('pipeline dict requires key "steps"')

    raw_name = data["name"]
    if not isinstance(raw_name, str) or not raw_name.strip():
        raise ValueError('pipeline "name" must be a non-empty string')

    raw_steps = data["steps"]
    if not isinstance(raw_steps, list):
        raise ValueError('pipeline "steps" must be a list')

    steps: list[StepAST] = []
    for item in raw_steps:
        steps.append(_step_ast_from_mapping(item))

    return PipelineAST(name=raw_name.strip(), steps=steps)


def _step_ast_from_mapping(item: Any) -> StepAST:
    if not isinstance(item, dict):
        raise ValueError("each step must be a dict")

    name = item.get("name")
    step_type = item.get("type")
    if not isinstance(name, str) or not name.strip():
        raise ValueError('each step requires non-empty string "name"')
    if not isinstance(step_type, str) or not step_type.strip():
        raise ValueError('each step requires non-empty string "type"')

    next_ref = item.get("next")
    if next_ref is not None and not isinstance(next_ref, str):
        raise ValueError('step "next" must be a string or omitted / null')

    raw_config = item.get("config")
    if raw_config is None:
        cfg: dict[str, Any] = {}
    elif isinstance(raw_config, dict):
        cfg = dict(raw_config)
    else:
        raise ValueError('step "config" must be a dict when present')

    reserved = {"name", "type", "config", "next"}
    for key, value in item.items():
        if key in reserved:
            continue
        if key in cfg:
            raise ValueError(f"duplicate step field {key!r} in config and top level")
        cfg[key] = value

    return StepAST(name=name.strip(), type=step_type.strip(), config=cfg, next=next_ref)


def _parse_pipeline_from_string(source: str) -> PipelineAST:
    s = source.strip()
    if not s:
        raise ValueError("pipeline name string must be non-empty")
    if any(ch in s for ch in "\n\r\t{}"):
        raise ValueError("pipeline name string must be a single-line name without braces")
    if " " in s:
        raise ValueError("pipeline name string must not contain whitespace")
    return PipelineAST(name=s, steps=[])


def check_pipeline(ast: PipelineAST) -> None:
    """
    Phase 3.2: structural validation of a ``PipelineAST`` (no security, compliance,
    AI, effect, saga, budget, or residency rules).
    """
    if not isinstance(ast, PipelineAST):
        raise TypeError("check_pipeline expected PipelineAST")

    if not isinstance(ast.name, str) or not ast.name.strip():
        raise ValueError("pipeline name must be a non-empty string")

    if not isinstance(ast.steps, list):
        raise ValueError("pipeline steps must be a list")

    name_set: set[str] = set()
    for i, step in enumerate(ast.steps):
        if not isinstance(step, StepAST):
            raise ValueError(f"pipeline steps[{i}] must be StepAST")
        if not isinstance(step.name, str) or not step.name.strip():
            raise ValueError(f"step at index {i} must have a non-empty name")
        if not isinstance(step.type, str) or not step.type.strip():
            raise ValueError(f"step {step.name!r} must have a non-empty type")
        if not isinstance(step.config, dict):
            raise ValueError(f"step {step.name!r} config must be a dict")
        canon = step.name.strip()
        if canon in name_set:
            raise ValueError(f"duplicate step name: {canon!r}")
        name_set.add(canon)

    for step in ast.steps:
        nxt = step.next
        if nxt is None:
            continue
        if not isinstance(nxt, str):
            raise ValueError(f"step {step.name!r} next must be str or None")
        target = nxt.strip()
        if target != nxt:
            raise ValueError(
                f"step {step.name!r} next must not have leading or trailing whitespace"
            )
        if target not in name_set:
            raise ValueError(f"step {step.name!r} next references unknown step {target!r}")

    if _next_chain_has_cycle(ast.steps, name_set):
        raise ValueError("cycle detected in step next chain")


def _next_chain_has_cycle(steps: list[StepAST], name_set: set[str]) -> bool:
    """True if following ``StepAST.next`` edges forms a directed cycle."""
    successors: dict[str, str] = {}
    for s in steps:
        if s.next is None:
            continue
        successors[s.name.strip()] = s.next.strip()

    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {n: WHITE for n in name_set}

    def dfs(node: str) -> bool:
        color[node] = GRAY
        succ = successors.get(node)
        if succ is None:
            color[node] = BLACK
            return False
        if succ not in color:
            return False
        if color[succ] == GRAY:
            return True
        if color[succ] == WHITE and dfs(succ):
            return True
        color[node] = BLACK
        return False

    for n in name_set:
        if color[n] == WHITE and dfs(n):
            return True
    return False


def generate_ir(ast: PipelineAST) -> IRPipeline:
    """
    Phase 3.3: lower a ``PipelineAST`` to a structural IR graph (no optimization or semantics).
    """
    if not isinstance(ast, PipelineAST):
        raise TypeError("generate_ir expected PipelineAST")

    nodes: dict[str, IRNode] = {}
    referenced: set[str] = set()

    for step in ast.steps:
        key = step.name.strip()
        nxt: list[str] = []
        if step.next is not None:
            target = step.next.strip()
            nxt = [target]
            referenced.add(target)
        nodes[key] = IRNode(
            name=key,
            type=step.type.strip(),
            config=dict(step.config),
            next=nxt,
        )

    entrypoints = [s.name.strip() for s in ast.steps if s.name.strip() not in referenced]
    if not entrypoints:
        raise ValueError("pipeline has no entrypoints")

    return IRPipeline(
        name=ast.name.strip(),
        nodes=nodes,
        entrypoints=entrypoints,
    )


def _normalize_next_targets(targets: list[str]) -> list[str]:
    stripped = [t.strip() for t in targets]
    non_empty = [t for t in stripped if t]
    return sorted(set(non_empty))


def optimize_ir(ir: IRPipeline) -> IRPipeline:
    """
    Phase 3.4: structural cleanup — normalized ``next`` edges, unreachable-node removal,
    deterministic ordering. No scheduling, batching, fusion, saga, or cost optimizations.
    """
    if not isinstance(ir, IRPipeline):
        raise TypeError("optimize_ir expected IRPipeline")

    out = copy.deepcopy(ir)

    for node in out.nodes.values():
        node.next = _normalize_next_targets(node.next)

    reachable: set[str] = set()
    queue: deque[str] = deque(ep for ep in out.entrypoints if ep in out.nodes)
    while queue:
        u = queue.popleft()
        if u in reachable:
            continue
        reachable.add(u)
        for v in out.nodes[u].next:
            if v in out.nodes and v not in reachable:
                queue.append(v)

    out.nodes = {k: out.nodes[k] for k in sorted(reachable) if k in out.nodes}

    for node in out.nodes.values():
        node.next = [t for t in node.next if t in out.nodes]

    referenced: set[str] = set()
    for node in out.nodes.values():
        referenced.update(node.next)

    out.entrypoints = sorted(n for n in out.nodes if n not in referenced)
    if not out.entrypoints:
        raise ValueError("no entrypoints after optimization")

    return out
