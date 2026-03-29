"""P14: lifecycle hooks (subprocess, stdin JSON)."""

from __future__ import annotations

import json
from pathlib import Path

import requests_mock
from arctis_ghost import cli


def _write_body(tmp: Path) -> None:
    (tmp / "body.json").write_text(
        json.dumps({"input": {"x": 1}}, sort_keys=True),
        encoding="utf-8",
    )


def test_pre_run_hook_receives_json_and_runs_before_post(monkeypatch, ghost_cwd, tmp_path) -> None:
    monkeypatch.setenv("ARCTIS_GHOST_API_BASE_URL", "http://stub")
    monkeypatch.setenv("ARCTIS_GHOST_WORKFLOW_ID", "wf-hook")
    monkeypatch.delenv("ARCTIS_API_KEY", raising=False)

    Path("hook.py").write_text(
        """
import json, pathlib, sys
p = json.load(sys.stdin)
pathlib.Path("hook_seen.json").write_text(json.dumps(p), encoding="utf-8")
sys.exit(0)
""".strip(),
        encoding="utf-8",
    )
    Path("ghost.yaml").write_text(
        """
profiles:
  default:
    api_base_url: "http://stub"
    workflow_id: "wf-hook"
    hook_pre_run: "hook.py"
    hook_timeout_seconds: 30
""",
        encoding="utf-8",
    )
    _write_body(Path("."))

    with requests_mock.Mocker() as m:
        m.post(
            "http://stub/customer/workflows/wf-hook/execute",
            status_code=201,
            headers={"X-Run-Id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"},
            json={},
        )
        code = cli.main(["run", "body.json"])

    assert code == 0
    seen = json.loads(Path("hook_seen.json").read_text(encoding="utf-8"))
    assert seen["hook"] == "pre_run"
    assert seen["workflow_id"] == "wf-hook"
    assert seen["execute_body"]["input"]["x"] == 1


def test_pre_run_nonzero_blocks_execute(monkeypatch, ghost_cwd, tmp_path) -> None:
    monkeypatch.setenv("ARCTIS_GHOST_API_BASE_URL", "http://stub")
    monkeypatch.setenv("ARCTIS_GHOST_WORKFLOW_ID", "wf-x")
    monkeypatch.delenv("ARCTIS_API_KEY", raising=False)

    Path("hook.py").write_text("import sys\nsys.exit(42)\n", encoding="utf-8")
    Path("ghost.yaml").write_text(
        """
profiles:
  default:
    hook_pre_run: "hook.py"
""",
        encoding="utf-8",
    )
    _write_body(Path("."))

    with requests_mock.Mocker() as m:
        m.post(
            "http://stub/customer/workflows/wf-x/execute",
            status_code=201,
            headers={"X-Run-Id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"},
            json={},
        )
        code = cli.main(["run", "body.json"])

    assert code == 1
    assert len(m.request_history) == 0


def test_post_run_hook_receives_run_id(monkeypatch, ghost_cwd, capsys) -> None:
    monkeypatch.setenv("ARCTIS_GHOST_API_BASE_URL", "http://stub")
    monkeypatch.setenv("ARCTIS_GHOST_WORKFLOW_ID", "wf-post")
    monkeypatch.delenv("ARCTIS_API_KEY", raising=False)

    Path("post.py").write_text(
        """
import json, pathlib, sys
p = json.load(sys.stdin)
pathlib.Path("post_run_id.txt").write_text(p.get("run_id") or "", encoding="utf-8")
sys.exit(0)
""".strip(),
        encoding="utf-8",
    )
    Path("ghost.yaml").write_text(
        """
profiles:
  default:
    workflow_id: "wf-post"
    hook_post_run: "post.py"
""",
        encoding="utf-8",
    )
    _write_body(Path("."))
    rid = "cccccccc-cccc-cccc-cccc-cccccccccccc"

    with requests_mock.Mocker() as m:
        m.post(
            "http://stub/customer/workflows/wf-post/execute",
            status_code=201,
            headers={"X-Run-Id": rid},
            json={},
        )
        code = cli.main(["run", "body.json"])

    assert code == 0
    assert Path("post_run_id.txt").read_text(encoding="utf-8") == rid
    assert capsys.readouterr().out.strip() == rid


def test_on_error_hook_after_http_error(monkeypatch, ghost_cwd) -> None:
    monkeypatch.setenv("ARCTIS_GHOST_API_BASE_URL", "http://stub")
    monkeypatch.setenv("ARCTIS_GHOST_WORKFLOW_ID", "wf-err")
    monkeypatch.delenv("ARCTIS_API_KEY", raising=False)

    Path("err.py").write_text(
        """
import json, pathlib, sys
json.load(sys.stdin)
pathlib.Path("saw_err").write_text("1", encoding="utf-8")
sys.exit(0)
""".strip(),
        encoding="utf-8",
    )
    Path("ghost.yaml").write_text(
        """
profiles:
  default:
    workflow_id: "wf-err"
    hook_on_error: "err.py"
""",
        encoding="utf-8",
    )
    _write_body(Path("."))

    with requests_mock.Mocker() as m:
        m.post(
            "http://stub/customer/workflows/wf-err/execute",
            status_code=500,
            json={"detail": "no"},
        )
        code = cli.main(["run", "body.json"])

    assert code == 1
    assert Path("saw_err").read_text(encoding="utf-8") == "1"


def test_no_hooks_skips_pre_run(monkeypatch, ghost_cwd) -> None:
    monkeypatch.setenv("ARCTIS_GHOST_API_BASE_URL", "http://stub")
    monkeypatch.setenv("ARCTIS_GHOST_WORKFLOW_ID", "wf-nh")
    monkeypatch.delenv("ARCTIS_API_KEY", raising=False)

    Path("hook.py").write_text(
        "import pathlib\npathlib.Path('ran').write_text('x')\nimport sys\nsys.exit(1)\n",
        encoding="utf-8",
    )
    Path("ghost.yaml").write_text(
        """
profiles:
  default:
    workflow_id: "wf-nh"
    hook_pre_run: "hook.py"
""",
        encoding="utf-8",
    )
    _write_body(Path("."))

    with requests_mock.Mocker() as m:
        m.post(
            "http://stub/customer/workflows/wf-nh/execute",
            status_code=201,
            headers={"X-Run-Id": "dddddddd-dddd-dddd-dddd-dddddddddddd"},
            json={},
        )
        code = cli.main(["run", "--no-hooks", "body.json"])

    assert code == 0
    assert not Path("ran").exists()


def test_dry_run_skips_hooks(monkeypatch, ghost_cwd) -> None:
    monkeypatch.setenv("ARCTIS_GHOST_API_BASE_URL", "http://stub")
    monkeypatch.delenv("ARCTIS_API_KEY", raising=False)

    Path("hook.py").write_text(
        "import pathlib\npathlib.Path('ran2').write_text('x')\n",
        encoding="utf-8",
    )
    Path("ghost.yaml").write_text(
        """
profiles:
  default:
    hook_pre_run: "hook.py"
""",
        encoding="utf-8",
    )
    _write_body(Path("."))

    code = cli.main(["run", "--dry-run", "body.json"])
    assert code == 0
    assert not Path("ran2").exists()
