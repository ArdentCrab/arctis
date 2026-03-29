"""Tests for ``ghost.yaml`` profiles and env overrides (C3)."""

from __future__ import annotations

from pathlib import Path

import pytest
from arctis_ghost.config import GhostConfigError, load_config


def test_load_config_warns_when_yaml_contains_api_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    for k in (
        "ARCTIS_GHOST_PROFILE",
        "ARCTIS_GHOST_API_BASE_URL",
        "ARCTIS_GHOST_WORKFLOW_ID",
        "ARCTIS_API_KEY",
        "ARCTIS_GHOST_CONFIG",
    ):
        monkeypatch.delenv(k, raising=False)
    (tmp_path / "ghost.yaml").write_text(
        """
active_profile: default
profiles:
  default:
    api_base_url: "http://x"
    api_key: "secret-in-file"
""",
        encoding="utf-8",
    )
    with pytest.warns(UserWarning, match="plaintext"):
        load_config()


def test_load_config_from_yaml_profiles(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ARCTIS_GHOST_PROFILE", raising=False)
    monkeypatch.delenv("ARCTIS_GHOST_API_BASE_URL", raising=False)
    monkeypatch.delenv("ARCTIS_GHOST_WORKFLOW_ID", raising=False)
    monkeypatch.delenv("ARCTIS_API_KEY", raising=False)
    monkeypatch.delenv("ARCTIS_GHOST_MAX_RETRIES_429", raising=False)
    monkeypatch.delenv("ARCTIS_GHOST_IDEMPOTENCY", raising=False)
    monkeypatch.delenv("ARCTIS_GHOST_CONFIG", raising=False)
    monkeypatch.delenv("ARCTIS_GHOST_ENVELOPE_AUDITED_BY", raising=False)
    monkeypatch.delenv("ARCTIS_GHOST_ENVELOPE_BRANDING_VERSION", raising=False)
    monkeypatch.delenv("ARCTIS_GHOST_PLG_STATUS_NOTE", raising=False)
    monkeypatch.delenv("ARCTIS_GHOST_PLG_STATUS_FILE", raising=False)

    (tmp_path / "ghost.yaml").write_text(
        """
active_profile: alpha
profiles:
  alpha:
    api_base_url: "http://alpha.example"
    workflow_id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    max_retries_429: 1
    generate_idempotency_key: false
  beta:
    api_base_url: "http://beta.example"
    workflow_id: "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
""",
        encoding="utf-8",
    )

    a = load_config()
    assert a.profile == "alpha"
    assert a.api_base_url == "http://alpha.example"
    assert a.workflow_id == "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    assert a.max_retries_429 == 1
    assert a.generate_idempotency_key is False

    b = load_config(profile="beta")
    assert b.profile == "beta"
    assert b.api_base_url == "http://beta.example"
    assert b.workflow_id == "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


def test_env_overrides_yaml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ARCTIS_GHOST_PROFILE", raising=False)
    monkeypatch.delenv("ARCTIS_GHOST_CONFIG", raising=False)
    monkeypatch.delenv("ARCTIS_GHOST_ENVELOPE_AUDITED_BY", raising=False)
    monkeypatch.delenv("ARCTIS_GHOST_ENVELOPE_BRANDING_VERSION", raising=False)
    monkeypatch.delenv("ARCTIS_GHOST_PLG_STATUS_NOTE", raising=False)
    monkeypatch.delenv("ARCTIS_GHOST_PLG_STATUS_FILE", raising=False)
    (tmp_path / "ghost.yaml").write_text(
        """
profiles:
  default:
    api_base_url: "http://from-yaml"
    workflow_id: "00000000-0000-0000-0000-000000000001"
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("ARCTIS_GHOST_API_BASE_URL", "http://from-env")
    monkeypatch.setenv("ARCTIS_GHOST_WORKFLOW_ID", "11111111-1111-1111-1111-111111111111")
    monkeypatch.setenv("ARCTIS_GHOST_MAX_RETRIES_429", "0")
    monkeypatch.setenv("ARCTIS_GHOST_IDEMPOTENCY", "on")

    c = load_config()
    assert c.api_base_url == "http://from-env"
    assert c.workflow_id == "11111111-1111-1111-1111-111111111111"
    assert c.max_retries_429 == 0
    assert c.generate_idempotency_key is True


def test_unknown_profile_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ARCTIS_GHOST_CONFIG", raising=False)
    (tmp_path / "ghost.yaml").write_text(
        "active_profile: default\nprofiles:\n  default: { workflow_id: x }\n",
        encoding="utf-8",
    )
    with pytest.raises(GhostConfigError, match="unknown profile"):
        load_config(profile="missing")


def test_explicit_config_path_missing_raises(tmp_path: Path) -> None:
    p = tmp_path / "nope.yaml"
    with pytest.raises(GhostConfigError, match="not found"):
        load_config(config_path=p)


def test_arctis_ghost_profile_env_selects_profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ARCTIS_GHOST_CONFIG", raising=False)
    monkeypatch.delenv("ARCTIS_GHOST_API_BASE_URL", raising=False)
    monkeypatch.delenv("ARCTIS_GHOST_WORKFLOW_ID", raising=False)
    monkeypatch.delenv("ARCTIS_GHOST_ENVELOPE_AUDITED_BY", raising=False)
    monkeypatch.delenv("ARCTIS_GHOST_ENVELOPE_BRANDING_VERSION", raising=False)
    monkeypatch.delenv("ARCTIS_GHOST_PLG_STATUS_NOTE", raising=False)
    monkeypatch.delenv("ARCTIS_GHOST_PLG_STATUS_FILE", raising=False)
    (tmp_path / "ghost.yaml").write_text(
        """
profiles:
  default:
    workflow_id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
  staging:
    workflow_id: "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("ARCTIS_GHOST_PROFILE", "staging")
    c = load_config()
    assert c.profile == "staging"
    assert c.workflow_id == "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


def test_plg_and_envelope_fields_from_yaml_and_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ARCTIS_GHOST_CONFIG", raising=False)
    monkeypatch.delenv("ARCTIS_GHOST_ENVELOPE_AUDITED_BY", raising=False)
    monkeypatch.delenv("ARCTIS_GHOST_ENVELOPE_BRANDING_VERSION", raising=False)
    monkeypatch.delenv("ARCTIS_GHOST_PLG_STATUS_NOTE", raising=False)
    monkeypatch.delenv("ARCTIS_GHOST_PLG_STATUS_FILE", raising=False)
    (tmp_path / "ghost.yaml").write_text(
        """
profiles:
  default:
    workflow_id: "00000000-0000-0000-0000-000000000001"
    envelope_audited_by: "From YAML"
    envelope_branding_version: "yaml-1"
    plg_status_note: "yaml note"
    plg_status_file_enabled: false
""",
        encoding="utf-8",
    )
    c = load_config()
    assert c.envelope_audited_by == "From YAML"
    assert c.envelope_branding_version == "yaml-1"
    assert c.plg_status_note == "yaml note"
    assert c.plg_status_file_enabled is False

    monkeypatch.setenv("ARCTIS_GHOST_ENVELOPE_AUDITED_BY", "From Env")
    monkeypatch.setenv("ARCTIS_GHOST_PLG_STATUS_FILE", "on")
    e = load_config()
    assert e.envelope_audited_by == "From Env"
    assert e.plg_status_file_enabled is True


def test_default_recipe_from_yaml_and_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ARCTIS_GHOST_CONFIG", raising=False)
    monkeypatch.delenv("ARCTIS_GHOST_DEFAULT_RECIPE", raising=False)
    (tmp_path / "ghost.yaml").write_text(
        """
profiles:
  default:
    workflow_id: "00000000-0000-0000-0000-000000000001"
    default_recipe: recipes/from-yaml.yaml
""",
        encoding="utf-8",
    )
    assert load_config().default_recipe == "recipes/from-yaml.yaml"

    monkeypatch.setenv("ARCTIS_GHOST_DEFAULT_RECIPE", "from-env.yaml")
    assert load_config().default_recipe == "from-env.yaml"


def test_hook_paths_from_yaml_and_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ARCTIS_GHOST_CONFIG", raising=False)
    monkeypatch.delenv("ARCTIS_GHOST_HOOK_PRE_RUN", raising=False)
    monkeypatch.delenv("ARCTIS_GHOST_HOOK_TIMEOUT", raising=False)
    (tmp_path / "ghost.yaml").write_text(
        """
profiles:
  default:
    workflow_id: "00000000-0000-0000-0000-000000000001"
    hook_pre_run: scripts/pre.py
    hook_timeout_seconds: 45
""",
        encoding="utf-8",
    )
    c = load_config()
    assert c.hook_pre_run == "scripts/pre.py"
    assert c.hook_timeout_seconds == 45.0

    monkeypatch.setenv("ARCTIS_GHOST_HOOK_PRE_RUN", "env_pre.py")
    monkeypatch.setenv("ARCTIS_GHOST_HOOK_TIMEOUT", "12")
    e = load_config()
    assert e.hook_pre_run == "env_pre.py"
    assert e.hook_timeout_seconds == 12.0
