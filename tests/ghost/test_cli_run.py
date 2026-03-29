"""CLI ``ghost run`` tests (HTTP mocked)."""

from __future__ import annotations

import json
from unittest.mock import patch

import requests_mock
from arctis_ghost import cli


def test_ghost_run_cli_posts_json_and_prints_run_id(monkeypatch, ghost_cwd, capsys) -> None:
    monkeypatch.setenv("ARCTIS_GHOST_API_BASE_URL", "http://stub")
    monkeypatch.setenv("ARCTIS_GHOST_WORKFLOW_ID", "my-workflow")
    monkeypatch.delenv("ARCTIS_API_KEY", raising=False)

    from pathlib import Path

    Path("body.json").write_text(
        json.dumps({"input": {"text": "hello"}}, sort_keys=True), encoding="utf-8"
    )

    with requests_mock.Mocker() as m:
        m.post(
            "http://stub/customer/workflows/my-workflow/execute",
            status_code=201,
            headers={"X-Run-Id": "11111111-2222-3333-4444-555555555555"},
            json={"result": {}, "schema_version": "1"},
        )
        code = cli.main(["run", "body.json"])

    assert code == 0
    assert capsys.readouterr().out.strip() == "11111111-2222-3333-4444-555555555555"
    assert m.last_request.json() == {"input": {"text": "hello"}}


def test_ghost_run_cli_requires_input_without_recipe(tmp_path, capsys) -> None:
    code = cli.main(["run"])
    assert code == 1
    assert "recipe" in capsys.readouterr().err.lower()


def test_ghost_run_cli_rejects_non_object_json(ghost_cwd, capsys) -> None:
    from pathlib import Path

    Path("bad.json").write_text("[1,2,3]", encoding="utf-8")
    code = cli.main(["run", "bad.json"])
    assert code == 1
    assert "object" in capsys.readouterr().err.lower()


def test_ghost_run_cli_recipe_posts_expected_body(monkeypatch, ghost_cwd, capsys) -> None:
    monkeypatch.setenv("ARCTIS_GHOST_API_BASE_URL", "http://stub")
    monkeypatch.setenv("ARCTIS_GHOST_WORKFLOW_ID", "ignored-when-recipe-sets")
    monkeypatch.delenv("ARCTIS_API_KEY", raising=False)

    from pathlib import Path

    Path("recipe.yaml").write_text(
        """
workflow_id: wf-from-recipe
defaults:
  input:
    base: true
skills:
  - id: cost_token_snapshot
input_mapping:
  mode: json
""".strip(),
        encoding="utf-8",
    )
    Path("payload.json").write_text('{"input": {"extra": 1}}', encoding="utf-8")

    with requests_mock.Mocker() as m:
        m.post(
            "http://stub/customer/workflows/wf-from-recipe/execute",
            status_code=201,
            headers={"X-Run-Id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"},
            json={"result": {}, "schema_version": "1"},
        )
        code = cli.main(["run", "--recipe", "recipe.yaml", "payload.json"])

    assert code == 0
    assert capsys.readouterr().out.strip() == "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    assert m.last_request.json() == {
        "input": {"base": True, "extra": 1},
        "skills": [{"id": "cost_token_snapshot"}],
    }


def test_ghost_run_dry_run_skips_http_json_body(monkeypatch, ghost_cwd, capsys) -> None:
    monkeypatch.setenv("ARCTIS_GHOST_API_BASE_URL", "http://stub")
    monkeypatch.setenv("ARCTIS_GHOST_WORKFLOW_ID", "wf-dry")
    monkeypatch.delenv("ARCTIS_API_KEY", raising=False)

    from pathlib import Path

    Path("body.json").write_text(
        json.dumps({"input": {"x": 1}}, sort_keys=True), encoding="utf-8"
    )

    with patch("arctis_ghost.cli.ghost_run") as gr:
        code = cli.main(["run", "--dry-run", "body.json"])
    assert code == 0
    gr.assert_not_called()
    cap = capsys.readouterr()
    assert "dry-run" in cap.err.lower()
    assert "wf-dry" in cap.err
    assert "customer/workflows/wf-dry/execute" in cap.err
    assert json.loads(cap.out) == {"input": {"x": 1}}


def test_ghost_run_dry_run_skips_http_recipe(monkeypatch, ghost_cwd, capsys) -> None:
    monkeypatch.setenv("ARCTIS_GHOST_API_BASE_URL", "http://stub")
    monkeypatch.setenv("ARCTIS_GHOST_WORKFLOW_ID", "ignored")
    monkeypatch.delenv("ARCTIS_API_KEY", raising=False)

    from pathlib import Path

    Path("recipe.yaml").write_text(
        """
workflow_id: wf-recipe-dry
skills:
  - id: cost_token_snapshot
input_mapping:
  mode: json
""".strip(),
        encoding="utf-8",
    )
    Path("in.json").write_text('{"input": {"n": 2}}', encoding="utf-8")

    with patch("arctis_ghost.cli.ghost_run") as gr:
        code = cli.main(["run", "--dry-run", "--recipe", "recipe.yaml", "in.json"])
    assert code == 0
    gr.assert_not_called()
    cap = capsys.readouterr()
    assert "wf-recipe-dry" in cap.err
    body = json.loads(cap.out)
    assert body["skills"] == [{"id": "cost_token_snapshot"}]
    assert body["input"] == {"n": 2}


def test_ghost_run_uses_yaml_default_recipe(monkeypatch, ghost_cwd, capsys) -> None:
    monkeypatch.setenv("ARCTIS_GHOST_API_BASE_URL", "http://stub")
    monkeypatch.setenv("ARCTIS_GHOST_WORKFLOW_ID", "ignored")
    monkeypatch.delenv("ARCTIS_API_KEY", raising=False)
    monkeypatch.delenv("ARCTIS_GHOST_DEFAULT_RECIPE", raising=False)

    from pathlib import Path

    Path("ghost.yaml").write_text(
        """
active_profile: default
profiles:
  default:
    api_base_url: "http://stub"
    default_recipe: "myrecipe.yaml"
""",
        encoding="utf-8",
    )
    Path("myrecipe.yaml").write_text(
        """
workflow_id: wf-prof-def
skills:
  - id: cost_token_snapshot
input_mapping:
  mode: json
""".strip(),
        encoding="utf-8",
    )
    Path("in.json").write_text('{"input": {"k": 1}}', encoding="utf-8")

    with requests_mock.Mocker() as m:
        m.post(
            "http://stub/customer/workflows/wf-prof-def/execute",
            status_code=201,
            headers={"X-Run-Id": "22222222-2222-2222-2222-222222222222"},
            json={"result": {}, "schema_version": "1"},
        )
        code = cli.main(["run", "in.json"])

    assert code == 0
    assert capsys.readouterr().out.strip() == "22222222-2222-2222-2222-222222222222"
    assert m.last_request.json()["skills"] == [{"id": "cost_token_snapshot"}]


def test_ghost_run_raw_json_ignores_default_recipe(monkeypatch, ghost_cwd, capsys) -> None:
    monkeypatch.setenv("ARCTIS_GHOST_API_BASE_URL", "http://stub")
    monkeypatch.setenv("ARCTIS_GHOST_WORKFLOW_ID", "wf-plain")
    monkeypatch.delenv("ARCTIS_API_KEY", raising=False)

    from pathlib import Path

    Path("ghost.yaml").write_text(
        """
profiles:
  default:
    default_recipe: "myrecipe.yaml"
""",
        encoding="utf-8",
    )
    Path("myrecipe.yaml").write_text(
        "workflow_id: should-not-load\nskills: []\ninput_mapping:\n  mode: json\n",
        encoding="utf-8",
    )
    Path("body.json").write_text(
        json.dumps({"input": {"only": True}, "skills": []}, sort_keys=True),
        encoding="utf-8",
    )

    with requests_mock.Mocker() as m:
        m.post(
            "http://stub/customer/workflows/wf-plain/execute",
            status_code=201,
            headers={"X-Run-Id": "33333333-3333-3333-3333-333333333333"},
            json={"result": {}, "schema_version": "1"},
        )
        code = cli.main(["run", "--raw-json", "body.json"])

    assert code == 0
    assert m.last_request.json() == {"input": {"only": True}, "skills": []}


def test_ghost_run_auto_recipe_finds_recipe_yaml(monkeypatch, ghost_cwd, capsys) -> None:
    monkeypatch.setenv("ARCTIS_GHOST_API_BASE_URL", "http://stub")
    monkeypatch.setenv("ARCTIS_GHOST_WORKFLOW_ID", "ignored")
    monkeypatch.delenv("ARCTIS_API_KEY", raising=False)
    monkeypatch.delenv("ARCTIS_GHOST_AUTO_RECIPE", raising=False)

    from pathlib import Path

    Path("recipe.yaml").write_text(
        """
workflow_id: wf-auto
skills:
  - id: cost_token_snapshot
input_mapping:
  mode: json
""".strip(),
        encoding="utf-8",
    )
    Path("in.json").write_text('{"input": {}}', encoding="utf-8")

    with requests_mock.Mocker() as m:
        m.post(
            "http://stub/customer/workflows/wf-auto/execute",
            status_code=201,
            headers={"X-Run-Id": "44444444-4444-4444-4444-444444444444"},
            json={"result": {}, "schema_version": "1"},
        )
        code = cli.main(["run", "--auto-recipe", "in.json"])

    assert code == 0
    assert m.last_request.json()["skills"] == [{"id": "cost_token_snapshot"}]


def test_ghost_run_rejects_recipe_with_raw_json(capsys) -> None:
    code = cli.main(["run", "--recipe", "x.yaml", "--raw-json", "b.json"])
    assert code == 1
    assert "raw-json" in capsys.readouterr().err.lower()


def test_ghost_verify_cli_ok(monkeypatch, ghost_cwd, capsys) -> None:
    monkeypatch.setenv("ARCTIS_GHOST_API_BASE_URL", "http://stub")
    monkeypatch.delenv("ARCTIS_API_KEY", raising=False)

    from pathlib import Path

    rid = "55555555-5555-5555-5555-555555555555"
    Path("outgoing").mkdir()
    env = {
        "schema_version": "1.0",
        "run_id": rid,
        "generated_at": "2020-01-01T00:00:00+00:00",
        "skill_report_keys": ["a"],
        "status": "success",
    }
    Path(f"outgoing/{rid}").mkdir(parents=True)
    Path(f"outgoing/{rid}/envelope.json").write_text(
        json.dumps(env, sort_keys=True),
        encoding="utf-8",
    )

    run_payload = {
        "run_id": rid,
        "status": "success",
        "execution_summary": {"skill_reports": {"a": {}}},
    }

    with requests_mock.Mocker() as m:
        m.get(f"http://stub/runs/{rid}", json=run_payload)
        code = cli.main(["verify", rid])

    assert code == 0
    assert "ok" in capsys.readouterr().out.lower()


def test_ghost_verify_cli_mismatch(monkeypatch, ghost_cwd, capsys) -> None:
    monkeypatch.setenv("ARCTIS_GHOST_API_BASE_URL", "http://stub")
    monkeypatch.delenv("ARCTIS_API_KEY", raising=False)

    from pathlib import Path

    rid = "66666666-6666-6666-6666-666666666666"
    Path("outgoing").mkdir()
    env = {
        "schema_version": "1.0",
        "run_id": rid,
        "skill_report_keys": [],
        "status": "success",
    }
    Path(f"outgoing/{rid}").mkdir(parents=True)
    Path(f"outgoing/{rid}/envelope.json").write_text(
        json.dumps(env, sort_keys=True),
        encoding="utf-8",
    )

    run_payload = {
        "run_id": rid,
        "status": "failed",
        "execution_summary": {},
    }

    with requests_mock.Mocker() as m:
        m.get(f"http://stub/runs/{rid}", json=run_payload)
        code = cli.main(["verify", rid])

    assert code == 1
    err = capsys.readouterr().err.lower()
    assert "mismatch" in err or "status" in err
