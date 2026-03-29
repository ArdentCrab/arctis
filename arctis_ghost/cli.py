"""Ghost CLI: run, fetch, verify, meta, evidence, explain, watch, doctor, …"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from arctis_ghost import ansi
from arctis_ghost.auto_recipe import suggest_recipe_path
from arctis_ghost.client import GhostHttpError, ghost_fetch, ghost_run
from arctis_ghost.config import GhostConfigError, load_config
from arctis_ghost.doctor import run_doctor
from arctis_ghost.errors import GhostInputError
from arctis_ghost.evidence import render_evidence
from arctis_ghost.explain import render_explain
from arctis_ghost.heartbeat import run_heartbeat_loop, validate_heartbeat_url
from arctis_ghost.hooks import GhostHookError, run_ghost_hook
from arctis_ghost.init_demo import run_init_demo
from arctis_ghost.meta import ghost_meta_dict
from arctis_ghost.recipes import (
    GhostRecipeError,
    build_execute_body,
    effective_workflow_id,
    load_recipe,
)
from arctis_ghost.state import fingerprint_execute_body, lookup_run_id, save_run_mapping
from arctis_ghost.util import load_json, print_json
from arctis_ghost.verify import verify_envelope_against_run
from arctis_ghost.watch import watch_run
from arctis_ghost.writer import write_plg_status_file, write_run_artifacts


def _hook_post_run_warn(
    cfg,
    body: dict[str, Any],
    wf: str,
    run_id: str,
    *,
    no_hooks: bool,
) -> None:
    if no_hooks:
        return
    try:
        rc = run_ghost_hook(
            "post_run",
            cfg,
            body=body,
            workflow_id=wf,
            run_id=run_id,
            ghost_exit_code=0,
        )
    except GhostHookError as e:
        print(ansi.warn(f"post_run hook: {e}"), file=sys.stderr)
        return
    if rc != 0:
        print(ansi.warn(f"post_run hook exited with code {rc}"), file=sys.stderr)


def _hook_on_error_warn(
    cfg,
    body: dict[str, Any],
    wf: str,
    message: str,
    *,
    no_hooks: bool,
) -> None:
    if no_hooks:
        return
    try:
        rc = run_ghost_hook(
            "on_error",
            cfg,
            body=body,
            workflow_id=wf,
            error_message=message,
        )
    except GhostHookError as e:
        print(ansi.warn(f"on_error hook: {e}"), file=sys.stderr)
        return
    if rc != 0:
        print(ansi.warn(f"on_error hook exited with code {rc}"), file=sys.stderr)


def _recipe_auto_enabled(args: argparse.Namespace) -> bool:
    if getattr(args, "auto_recipe", False):
        return True
    raw = os.environ.get("ARCTIS_GHOST_AUTO_RECIPE", "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _resolve_recipe_path(args: argparse.Namespace, cfg) -> str | None:
    """Recipe YAML path, or ``None`` for plain JSON body (``--raw-json`` / no recipe)."""
    if getattr(args, "raw_json", False):
        return None
    if args.recipe:
        return args.recipe
    dr = (cfg.default_recipe or "").strip()
    if dr:
        return dr
    if _recipe_auto_enabled(args):
        return suggest_recipe_path()
    return None


def _run_cmd(args: argparse.Namespace) -> int:
    try:
        cfg = load_config(profile=args.ghost_profile)
    except GhostConfigError as e:
        print(ansi.error(f"Error: {e}"), file=sys.stderr)
        return 1

    if args.recipe and getattr(args, "raw_json", False):
        print(
            ansi.error("Error: cannot combine --recipe with --raw-json."),
            file=sys.stderr,
        )
        return 1

    recipe_path = _resolve_recipe_path(args, cfg)
    recipe = None
    if recipe_path:
        try:
            recipe = load_recipe(recipe_path)
        except GhostRecipeError as e:
            print(ansi.error(f"Error: {e}"), file=sys.stderr)
            return 1
        if args.recipe_input:
            in_path = Path(args.recipe_input)
        elif args.input_file:
            in_path = Path(args.input_file)
        else:
            in_path = None
        merge_path = Path(args.merge_json) if args.merge_json else None
        try:
            body = build_execute_body(recipe, input_path=in_path, merge_json_path=merge_path)
        except GhostRecipeError as e:
            print(ansi.error(f"Error: {e}"), file=sys.stderr)
            return 1
    else:
        if not args.input_file:
            print(
                ansi.error(
                    "Error: provide a JSON file, use --recipe / profile default_recipe, "
                    "or enable auto-recipe (--auto-recipe or ARCTIS_GHOST_AUTO_RECIPE=1)."
                ),
                file=sys.stderr,
            )
            return 1
        try:
            body = load_json(args.input_file)
        except GhostInputError as e:
            print(ansi.error(f"Error: {e}"), file=sys.stderr)
            return 1
        if not isinstance(body, dict):
            print(
                ansi.error('Error: JSON root must be an object (e.g. {"input": {...}})'),
                file=sys.stderr,
            )
            return 1

    if not isinstance(body, dict):
        print(ansi.error("Error: execute body must be a JSON object"), file=sys.stderr)
        return 1

    wf = effective_workflow_id(cfg=cfg, recipe=recipe, cli_workflow_id=args.cli_workflow_id)

    if args.run_dry_run:
        print(
            ansi.warn("Dry-run: no HTTP request; execute body below (stdout)."),
            file=sys.stderr,
        )
        print(f"effective_workflow_id: {wf}", file=sys.stderr)
        post_url = f"{cfg.api_base_url}/customer/workflows/{wf}/execute"
        print(f"POST would target: {post_url}", file=sys.stderr)
        print_json(body)
        return 0

    if cfg.state_enabled and not args.run_force:
        fp = fingerprint_execute_body(body, wf)
        cached = lookup_run_id(cfg, fp)
        if cached is not None:
            print(
                ansi.warn(
                    "Reusing cached run_id (local state; use --force to execute again)."
                ),
                file=sys.stderr,
            )
            print(cached)
            return 0

    no_hooks = bool(getattr(args, "run_no_hooks", False))
    if not no_hooks:
        try:
            pre_rc = run_ghost_hook("pre_run", cfg, body=body, workflow_id=wf)
        except GhostHookError as e:
            print(ansi.error(f"pre_run hook: {e}"), file=sys.stderr)
            return 1
        if pre_rc != 0:
            print(ansi.error(f"pre_run hook exited with code {pre_rc}"), file=sys.stderr)
            return 1
    try:
        run_id = ghost_run(body, config=cfg, workflow_id=wf)
    except GhostHttpError as e:
        msg = f"HTTP {e.status_code}: {e}"
        print(ansi.error(f"Error: {msg}"), file=sys.stderr)
        _hook_on_error_warn(cfg, body, wf, msg, no_hooks=no_hooks)
        return 1
    except (OSError, ValueError) as e:
        msg = str(e)
        print(ansi.error(f"Error: {e}"), file=sys.stderr)
        _hook_on_error_warn(cfg, body, wf, msg, no_hooks=no_hooks)
        return 1
    if cfg.state_enabled and not args.run_force:
        fp = fingerprint_execute_body(body, wf)
        save_run_mapping(cfg, fp, run_id, workflow_id=wf)
    _hook_post_run_warn(cfg, body, wf, run_id, no_hooks=no_hooks)
    print(run_id)
    return 0


def _fetch_cmd(args: argparse.Namespace) -> int:
    try:
        cfg = load_config(profile=args.ghost_profile)
    except GhostConfigError as e:
        print(ansi.error(f"Error: {e}"), file=sys.stderr)
        return 1
    try:
        obj = ghost_fetch(args.run_id, config=cfg)
    except GhostHttpError as e:
        print(ansi.error(f"Error: HTTP {e.status_code}: {e}"), file=sys.stderr)
        return 1
    except OSError as e:
        print(ansi.error(f"Error: {e}"), file=sys.stderr)
        return 1
    print_json(obj)
    return 0


def _evidence_cmd(args: argparse.Namespace) -> int:
    try:
        cfg = load_config(profile=args.ghost_profile)
    except GhostConfigError as e:
        print(ansi.error(f"Error: {e}"), file=sys.stderr)
        return 1
    try:
        run = ghost_fetch(args.run_id, config=cfg)
    except GhostHttpError as e:
        print(ansi.error(f"Error: HTTP {e.status_code}: {e}"), file=sys.stderr)
        return 1
    except OSError as e:
        print(ansi.error(f"Error: {e}"), file=sys.stderr)
        return 1
    render_evidence(run)
    return 0


def _explain_cmd(args: argparse.Namespace) -> int:
    try:
        cfg = load_config(profile=args.ghost_profile)
    except GhostConfigError as e:
        print(ansi.error(f"Error: {e}"), file=sys.stderr)
        return 1
    try:
        run = ghost_fetch(args.run_id, config=cfg)
    except GhostHttpError as e:
        print(ansi.error(f"Error: HTTP {e.status_code}: {e}"), file=sys.stderr)
        return 1
    except OSError as e:
        print(ansi.error(f"Error: {e}"), file=sys.stderr)
        return 1
    render_explain(run)
    return 0


def _watch_cmd(args: argparse.Namespace) -> int:
    try:
        cfg = load_config(profile=args.ghost_profile)
    except GhostConfigError as e:
        print(ansi.error(f"Error: {e}"), file=sys.stderr)
        return 1
    return watch_run(args.run_id, config=cfg)


def _heartbeat_cmd(args: argparse.Namespace) -> int:
    try:
        cfg = load_config(profile=args.ghost_profile)
    except GhostConfigError as e:
        print(ansi.error(f"Error: {e}"), file=sys.stderr)
        return 1

    url_cli = (args.hb_url or "").strip() if args.hb_url else ""
    url = url_cli or (cfg.heartbeat_url or "").strip() or None
    met_cli = (args.hb_metrics or "").strip() if args.hb_metrics else ""
    metrics = met_cli or (cfg.heartbeat_metrics_file or "").strip() or None
    use_health = bool(args.use_api_health)

    if not url and not use_health and not metrics:
        print(
            ansi.error(
                "Error: use --url, --use-api-health, and/or --metrics-file "
                "(or set heartbeat_* in ghost.yaml / ARCTIS_GHOST_HEARTBEAT_* env)."
            ),
            file=sys.stderr,
        )
        return 1

    if args.hb_count < 1 or args.hb_count > 100_000:
        print(ansi.error("Error: --count must be between 1 and 100000."), file=sys.stderr)
        return 1

    interval = (
        float(args.hb_interval) if args.hb_interval is not None else cfg.heartbeat_interval_seconds
    )

    if url:
        try:
            validate_heartbeat_url(url)
        except ValueError as e:
            print(ansi.error(f"Error: {e}"), file=sys.stderr)
            return 1

    try:
        return run_heartbeat_loop(
            url=url,
            use_api_health=use_health,
            api_base_url=cfg.api_base_url,
            metrics_rel_path=metrics,
            interval_seconds=interval,
            count=args.hb_count,
        )
    except ValueError as e:
        print(ansi.error(f"Error: {e}"), file=sys.stderr)
        return 1


def _doctor_cmd(args: argparse.Namespace) -> int:
    try:
        cfg = load_config(profile=args.ghost_profile)
    except GhostConfigError as e:
        print(ansi.error(f"Error: {e}"), file=sys.stderr)
        return 1
    return run_doctor(cfg)


def _pull_artifacts_cmd(args: argparse.Namespace) -> int:
    try:
        cfg = load_config(profile=args.ghost_profile)
    except GhostConfigError as e:
        print(ansi.error(f"Error: {e}"), file=sys.stderr)
        return 1
    try:
        run = ghost_fetch(args.run_id, config=cfg)
    except GhostHttpError as e:
        print(ansi.error(f"Error: HTTP {e.status_code}: {e}"), file=sys.stderr)
        return 1
    except OSError as e:
        print(ansi.error(f"Error: {e}"), file=sys.stderr)
        return 1
    root = Path(cfg.outgoing_root)
    try:
        out_dir = write_run_artifacts(run, root=root, cfg=cfg, overwrite=args.pull_force)
        write_plg_status_file(root, run_id=args.run_id, cfg=cfg)
    except (OSError, ValueError) as e:
        print(ansi.error(f"Error: {e}"), file=sys.stderr)
        return 1
    print(ansi.ok(f"Wrote artifacts under {out_dir}") + "\n")
    return 0


def _init_demo_cmd(args: argparse.Namespace) -> int:
    target = Path(args.demo_dir)
    try:
        run_init_demo(target, force=args.init_demo_force)
    except FileExistsError as e:
        print(ansi.error(f"Error: {e} (use --force to overwrite)"), file=sys.stderr)
        return 1
    except OSError as e:
        print(ansi.error(f"Error: {e}"), file=sys.stderr)
        return 1
    print(ansi.ok(f"Demo files created in {target.resolve()}") + "\n")
    return 0


def _meta_cmd(_args: argparse.Namespace) -> int:
    try:
        cfg = load_config(profile=_args.ghost_profile)
    except GhostConfigError as e:
        print(ansi.error(f"Error: {e}"), file=sys.stderr)
        return 1
    print_json(ghost_meta_dict(cfg))
    return 0


def _verify_cmd(args: argparse.Namespace) -> int:
    try:
        cfg = load_config(profile=args.ghost_profile)
    except GhostConfigError as e:
        print(ansi.error(f"Error: {e}"), file=sys.stderr)
        return 1
    try:
        run = ghost_fetch(args.run_id, config=cfg)
    except GhostHttpError as e:
        print(ansi.error(f"Error: HTTP {e.status_code}: {e}"), file=sys.stderr)
        return 1
    except OSError as e:
        print(ansi.error(f"Error: {e}"), file=sys.stderr)
        return 1
    if args.verify_envelope:
        env_path = args.verify_envelope
    else:
        env_path = Path(cfg.outgoing_root) / args.run_id / "envelope.json"
    ok, msgs = verify_envelope_against_run(run, env_path, cfg=cfg)
    if ok:
        print(ansi.ok("envelope verify: OK") + "\n")
        return 0
    print(ansi.error("envelope verify: mismatch"), file=sys.stderr)
    for m in msgs:
        print(ansi.error(f"  {m}"), file=sys.stderr)
    return 1


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ghost", description="Arctis Ghost CLI (MVP).")
    parser.add_argument(
        "--profile",
        dest="ghost_profile",
        default=None,
        help="Named profile from ghost.yaml (overrides ARCTIS_GHOST_PROFILE).",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    run_p = sub.add_parser(
        "run",
        help="POST customer execute from a JSON file or from a recipe (--recipe) plus --input.",
    )
    run_p.add_argument(
        "input_file",
        nargs="?",
        default=None,
        help="JSON body when not using --recipe; with --recipe, optional shorthand for --input.",
    )
    run_p.add_argument(
        "--recipe",
        metavar="PATH",
        default=None,
        help="Recipe YAML (workflow_id, skills, defaults, input_mapping).",
    )
    run_p.add_argument(
        "--input",
        dest="recipe_input",
        metavar="PATH",
        default=None,
        help="Input file for the recipe (JSON or text per recipe input_mapping).",
    )
    run_p.add_argument(
        "--merge-json",
        dest="merge_json",
        metavar="PATH",
        default=None,
        help="Optional JSON object merged last into the execute body (after recipe file merge).",
    )
    run_p.add_argument(
        "--workflow-id",
        dest="cli_workflow_id",
        default=None,
        help="Override workflow id for this run (CLI > recipe > ghost.yaml/env).",
    )
    run_p.add_argument(
        "--force",
        dest="run_force",
        action="store_true",
        help="Skip local state reuse and always POST a new run.",
    )
    run_p.add_argument(
        "--dry-run",
        dest="run_dry_run",
        action="store_true",
        help="Validate inputs and print execute JSON + workflow_id; do not POST (P10 sandbox).",
    )
    run_p.add_argument(
        "--raw-json",
        dest="raw_json",
        action="store_true",
        help=(
            "Treat input_file as the full execute body "
            "(ignore profile default_recipe and auto-recipe)."
        ),
    )
    run_p.add_argument(
        "--auto-recipe",
        dest="auto_recipe",
        action="store_true",
        help=(
            "P12: if no --recipe and no profile default, use recipe.yaml or "
            "recipes/<cwd>.yaml when present."
        ),
    )
    run_p.add_argument(
        "--no-hooks",
        dest="run_no_hooks",
        action="store_true",
        help="P14: skip lifecycle hooks (pre/post/on_error) for this run.",
    )

    verify_p = sub.add_parser(
        "verify",
        help="P12: compare local envelope.json to GET /runs/{id} (same fields as pull-artifacts).",
    )
    verify_p.add_argument("run_id", help="Run UUID")
    verify_p.add_argument(
        "--envelope",
        dest="verify_envelope",
        metavar="PATH",
        default=None,
        help="Path to envelope.json (default: outgoing_root/<run_id>/envelope.json).",
    )

    sub.add_parser(
        "meta",
        help="P13: print read-only config/runtime summary and roadmap labels (JSON).",
    )

    sub.add_parser(
        "doctor",
        help="Check config and API (GET /health; GET /pipelines if API key set).",
    )

    hb_p = sub.add_parser(
        "heartbeat",
        help="P11: optional loop — HTTP ping and/or append NDJSON metrics (opt-in; no daemon).",
    )
    hb_p.add_argument(
        "--url",
        dest="hb_url",
        default=None,
        metavar="URL",
        help="GET this URL each tick (http/https). Overrides profile/env default.",
    )
    hb_p.add_argument(
        "--use-api-health",
        action="store_true",
        help="GET {api_base_url}/health each tick (from ghost.yaml / env).",
    )
    hb_p.add_argument(
        "--metrics-file",
        dest="hb_metrics",
        default=None,
        metavar="PATH",
        help="Append one JSON line per tick (path relative to CWD).",
    )
    hb_p.add_argument(
        "--interval",
        dest="hb_interval",
        type=float,
        default=None,
        metavar="SEC",
        help="Seconds between ticks (default: profile or 30).",
    )
    hb_p.add_argument(
        "--count",
        dest="hb_count",
        type=int,
        default=1,
        metavar="N",
        help="Number of iterations (1–100000, default 1).",
    )

    fetch_p = sub.add_parser("fetch", help="GET /runs/{run_id} and print JSON.")
    fetch_p.add_argument("run_id", help="Run UUID")

    evidence_p = sub.add_parser("evidence", help="GET /runs/{run_id} and render evidence sections.")
    evidence_p.add_argument("run_id", help="Run UUID")

    explain_p = sub.add_parser(
        "explain",
        help="GET /runs/{run_id} and print a short read-only summary (no full skill JSON).",
    )
    explain_p.add_argument("run_id", help="Run UUID")

    watch_p = sub.add_parser("watch", help="Poll /runs/{run_id} until success or failure.")
    watch_p.add_argument("run_id", help="Run UUID")

    pull_p = sub.add_parser(
        "pull-artifacts",
        help="GET /runs/{run_id} and write envelope.json + skill_reports/ under outgoing_root.",
    )
    pull_p.add_argument("run_id", help="Run UUID")
    pull_p.add_argument(
        "--force",
        dest="pull_force",
        action="store_true",
        help="Overwrite an existing outgoing/<run_id>/ directory.",
    )

    init_p = sub.add_parser(
        "init-demo",
        help="Create ghost.yaml, input.json, README in a directory.",
    )
    init_p.add_argument(
        "demo_dir",
        nargs="?",
        default=".",
        help="Target directory (default: current).",
    )
    init_p.add_argument(
        "--force",
        dest="init_demo_force",
        action="store_true",
        help="Overwrite existing demo files.",
    )

    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.cmd == "run":
        return _run_cmd(args)
    if args.cmd == "verify":
        return _verify_cmd(args)
    if args.cmd == "meta":
        return _meta_cmd(args)
    if args.cmd == "doctor":
        return _doctor_cmd(args)
    if args.cmd == "heartbeat":
        return _heartbeat_cmd(args)
    if args.cmd == "fetch":
        return _fetch_cmd(args)
    if args.cmd == "evidence":
        return _evidence_cmd(args)
    if args.cmd == "explain":
        return _explain_cmd(args)
    if args.cmd == "watch":
        return _watch_cmd(args)
    if args.cmd == "pull-artifacts":
        return _pull_artifacts_cmd(args)
    if args.cmd == "init-demo":
        return _init_demo_cmd(args)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
