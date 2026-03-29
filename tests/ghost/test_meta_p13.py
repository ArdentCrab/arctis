"""P13: ``ghost meta`` read-only introspection."""

from __future__ import annotations

import json

from arctis_ghost import cli
from arctis_ghost.config import GhostConfig
from arctis_ghost.meta import ghost_meta_dict


def test_ghost_meta_dict_never_contains_api_key_secret() -> None:
    cfg = GhostConfig(
        api_base_url="http://x",
        workflow_id="w",
        api_key="super-secret-do-not-leak",
        profile="p",
        max_retries_429=0,
        generate_idempotency_key=False,
        outgoing_root="out",
        state_enabled=False,
        state_dir=".ghost/state",
    )
    raw = json.dumps(ghost_meta_dict(cfg))
    assert "super-secret" not in raw
    assert '"api_key"' not in raw
    d = ghost_meta_dict(cfg)
    assert d["config"]["credentials_configured"] is True


def test_ghost_meta_dict_roadmap_labels() -> None:
    cfg = GhostConfig()
    d = ghost_meta_dict(cfg)
    assert d["schema_version"] == "1.0"
    assert d["kind"] == "ghost_meta"
    assert d["capabilities"]["predict"]["status"] == "roadmap"
    assert d["capabilities"]["multi_region"]["status"] == "pilot"
    assert d["capabilities"]["lifecycle_hooks"]["status"] == "pilot"


def test_ghost_meta_cli_prints_json(ghost_cwd, capsys) -> None:
    code = cli.main(["meta"])
    assert code == 0
    out = capsys.readouterr().out
    obj = json.loads(out)
    assert obj["kind"] == "ghost_meta"
    assert "config" in obj
    assert "runtime" in obj
