"""Ghost configuration: ``ghost.yaml`` + profiles + env overrides (C3)."""

from __future__ import annotations

import os
import warnings
from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

# ---------------------------------------------------------------------------
# YAML schema (§6.1)
# ---------------------------------------------------------------------------


class GhostProfileYaml(BaseModel):
    """One named profile; omitted fields keep global defaults."""

    model_config = ConfigDict(extra="ignore")

    api_base_url: str | None = None
    workflow_id: str | None = None
    api_key: str | None = None
    max_retries_429: int | None = Field(default=None, ge=0, le=50)
    generate_idempotency_key: bool | None = None
    #: Artefakt-Root für :mod:`arctis_ghost.writer` (relativ zu CWD).
    outgoing_root: str | None = None
    state_enabled: bool | None = None
    state_dir: str | None = None
    #: Optional ``envelope.json`` branding (local artifact; not cryptographic proof).
    envelope_audited_by: str | None = None
    envelope_branding_version: str | None = None
    #: Extra line in ``outgoing_root/__STATUS.txt`` (pull-artifacts).
    plg_status_note: str | None = None
    plg_status_file_enabled: bool | None = None
    #: P11: default URL for ``ghost heartbeat`` when no ``--url`` (optional).
    heartbeat_url: str | None = None
    #: P11: append NDJSON heartbeat lines here (path relative to CWD).
    heartbeat_metrics_file: str | None = None
    heartbeat_interval_seconds: float | None = Field(default=None, ge=0.0, le=86400.0)
    #: P12: recipe YAML when ``--recipe`` omitted (unless ``--raw-json``).
    default_recipe: str | None = None
    #: P14: optional ``ghost run`` hooks (paths relative to CWD).
    hook_pre_run: str | None = None
    hook_post_run: str | None = None
    hook_on_error: str | None = None
    hook_timeout_seconds: float | None = Field(default=None, ge=0.5, le=600.0)


class GhostYamlFile(BaseModel):
    """Root object in ``ghost.yaml``."""

    model_config = ConfigDict(extra="ignore")

    active_profile: str = "default"
    profiles: dict[str, GhostProfileYaml] = Field(default_factory=dict)

    @field_validator("profiles")
    @classmethod
    def _non_empty_keys(cls, v: dict[str, GhostProfileYaml]) -> dict[str, GhostProfileYaml]:
        for k in v:
            if not str(k).strip():
                raise ValueError("profile names must be non-empty strings")
        return v


class GhostConfigError(ValueError):
    """Invalid config file, unknown profile, or bad env value."""


# ---------------------------------------------------------------------------
# Resolved runtime config (immutable)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class GhostConfig:
    """Effective settings for HTTP client and CLI."""

    api_base_url: str = "http://localhost:8000"
    workflow_id: str = "default"
    api_key: str = ""
    profile: str = "default"
    max_retries_429: int = 3
    generate_idempotency_key: bool = True
    outgoing_root: str = "outgoing"
    state_enabled: bool = False
    state_dir: str = ".ghost/state"
    envelope_audited_by: str = ""
    envelope_branding_version: str = ""
    plg_status_note: str = ""
    plg_status_file_enabled: bool = True
    heartbeat_url: str = ""
    heartbeat_metrics_file: str = ""
    heartbeat_interval_seconds: float = 30.0
    default_recipe: str = ""
    hook_pre_run: str = ""
    hook_post_run: str = ""
    hook_on_error: str = ""
    hook_timeout_seconds: float = 30.0


def _parse_float_interval(raw: str | None, *, env_name: str) -> float | None:
    if raw is None or not str(raw).strip():
        return None
    try:
        x = float(str(raw).strip())
    except ValueError as e:
        raise GhostConfigError(f"{env_name} must be a number") from e
    if x < 0 or x > 86400:
        raise GhostConfigError(f"{env_name} must be between 0 and 86400")
    return x


def _parse_positive_int(raw: str | None, *, env_name: str) -> int | None:
    if raw is None or not str(raw).strip():
        return None
    try:
        n = int(str(raw).strip(), 10)
    except ValueError as e:
        raise GhostConfigError(f"{env_name} must be an integer") from e
    if n < 0 or n > 50:
        raise GhostConfigError(f"{env_name} must be between 0 and 50")
    return n


def _parse_bool(raw: str | None, *, env_name: str = "boolean env") -> bool | None:
    if raw is None or not str(raw).strip():
        return None
    s = str(raw).strip().lower()
    if s in ("1", "true", "yes", "on"):
        return True
    if s in ("0", "false", "no", "off"):
        return False
    raise GhostConfigError(f"{env_name} must be 0/1, true/false, on/off")


def _warn_plaintext_api_key_in_yaml(config_path: Path, root: GhostYamlFile) -> None:
    for pname, prof in root.profiles.items():
        if prof.api_key and str(prof.api_key).strip():
            warnings.warn(
                f"{config_path}: profile {pname!r} stores api_key in plaintext on disk; "
                "prefer environment variable ARCTIS_API_KEY (see docs/security_production.md).",
                UserWarning,
                stacklevel=2,
            )


def _load_yaml_file(path: Path) -> GhostYamlFile:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        raise GhostConfigError(f"cannot read config file {path}: {e}") from e
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise GhostConfigError(f"invalid YAML in {path}: {e}") from e
    if raw is None:
        return GhostYamlFile()
    if not isinstance(raw, dict):
        raise GhostConfigError(f"{path}: root must be a mapping")
    try:
        return GhostYamlFile.model_validate(raw)
    except ValidationError as e:
        raise GhostConfigError(str(e)) from e


def _default_config_path() -> Path | None:
    env_path = os.environ.get("ARCTIS_GHOST_CONFIG", "").strip()
    if env_path:
        p = Path(env_path)
        return p if p.is_file() else None
    cwd = Path.cwd() / "ghost.yaml"
    return cwd if cwd.is_file() else None


def load_config(
    *,
    profile: str | None = None,
    config_path: str | Path | None = None,
) -> GhostConfig:
    """
    Resolve :class:`GhostConfig`.

    Precedence (lowest → highest): built-in defaults → ``ghost.yaml`` profile → environment.

    **Config file discovery**

    1. ``config_path`` argument (if provided and exists).
    2. ``ARCTIS_GHOST_CONFIG`` when set to an existing file.
    3. ``./ghost.yaml`` in the current working directory.

    **Profile selection**

    1. ``profile`` argument to :func:`load_config`.
    2. ``ARCTIS_GHOST_PROFILE``.
    3. ``active_profile`` from YAML.
    4. ``default``.

    **Environment overrides** (always win when set)

    - ``ARCTIS_GHOST_API_BASE_URL``
    - ``ARCTIS_GHOST_WORKFLOW_ID``
    - ``ARCTIS_API_KEY``
    - ``ARCTIS_GHOST_MAX_RETRIES_429`` (0–50)
    - ``ARCTIS_GHOST_IDEMPOTENCY`` — ``on``/``off`` (or ``1``/``0``) toggles
      ``generate_idempotency_key``.
    - ``ARCTIS_GHOST_OUTGOING_ROOT`` — Basisordner für Run-Artefakte (Writer).
    - ``ARCTIS_GHOST_STATE_ENABLED`` — ``on``/``off`` aktiviert Client-State (Skip/Reuse).
    - ``ARCTIS_GHOST_STATE_DIR`` — State-Ordner (default ``.ghost/state``).
    - ``ARCTIS_GHOST_ENVELOPE_AUDITED_BY`` — optional,
      ``envelope.json`` → ``branding.audited_by``.
    - ``ARCTIS_GHOST_ENVELOPE_BRANDING_VERSION`` — optional,
      ``branding.branding_version``.
    - ``ARCTIS_GHOST_PLG_STATUS_NOTE`` — Zusatzzeile in ``__STATUS.txt``.
    - ``ARCTIS_GHOST_PLG_STATUS_FILE`` — ``on``/``off`` für ``__STATUS.txt``
      bei ``pull-artifacts`` (default an).
    - ``ARCTIS_GHOST_HEARTBEAT_URL`` / ``ARCTIS_GHOST_HEARTBEAT_METRICS_FILE`` /
      ``ARCTIS_GHOST_HEARTBEAT_INTERVAL`` — Defaults für ``ghost heartbeat`` (P11).
    - ``ARCTIS_GHOST_DEFAULT_RECIPE`` — optional default recipe path (P12).
    - ``ARCTIS_GHOST_HOOK_PRE_RUN`` / ``_POST_RUN`` / ``_ON_ERROR`` — optional hook scripts (P14).
    - ``ARCTIS_GHOST_HOOK_TIMEOUT`` — hook subprocess timeout in seconds (P14).
    """
    if config_path is not None:
        path = Path(config_path)
        if not path.is_file():
            raise GhostConfigError(f"config file not found: {path}")
    else:
        path = _default_config_path()
    root: GhostYamlFile | None = _load_yaml_file(path) if path is not None else None
    if path is not None and root is not None and root.profiles:
        _warn_plaintext_api_key_in_yaml(path, root)

    profile_name = profile or os.environ.get("ARCTIS_GHOST_PROFILE", "").strip()
    if not profile_name and root is not None:
        profile_name = root.active_profile
    if not profile_name:
        profile_name = "default"

    api_base_url = "http://localhost:8000"
    workflow_id = "default"
    api_key = ""
    max_retries_429 = 3
    generate_idempotency_key = True
    outgoing_root = "outgoing"
    state_enabled = False
    state_dir = ".ghost/state"
    envelope_audited_by = ""
    envelope_branding_version = ""
    plg_status_note = ""
    plg_status_file_enabled = True
    heartbeat_url = ""
    heartbeat_metrics_file = ""
    heartbeat_interval_seconds = 30.0
    default_recipe = ""
    hook_pre_run = ""
    hook_post_run = ""
    hook_on_error = ""
    hook_timeout_seconds = 30.0

    if root is not None and root.profiles:
        if profile_name not in root.profiles:
            known = ", ".join(sorted(root.profiles))
            raise GhostConfigError(f"unknown profile {profile_name!r}; known: {known}")
        prof = root.profiles[profile_name]
        if prof.api_base_url is not None:
            api_base_url = prof.api_base_url.strip()
        if prof.workflow_id is not None:
            workflow_id = str(prof.workflow_id).strip()
        if prof.api_key is not None:
            api_key = str(prof.api_key).strip()
        if prof.max_retries_429 is not None:
            max_retries_429 = prof.max_retries_429
        if prof.generate_idempotency_key is not None:
            generate_idempotency_key = prof.generate_idempotency_key
        if prof.outgoing_root is not None:
            outgoing_root = str(prof.outgoing_root).strip()
        if prof.state_enabled is not None:
            state_enabled = prof.state_enabled
        if prof.state_dir is not None:
            state_dir = str(prof.state_dir).strip()
        if prof.envelope_audited_by is not None:
            envelope_audited_by = str(prof.envelope_audited_by).strip()
        if prof.envelope_branding_version is not None:
            envelope_branding_version = str(prof.envelope_branding_version).strip()
        if prof.plg_status_note is not None:
            plg_status_note = str(prof.plg_status_note).strip()
        if prof.plg_status_file_enabled is not None:
            plg_status_file_enabled = prof.plg_status_file_enabled
        if prof.heartbeat_url is not None:
            heartbeat_url = str(prof.heartbeat_url).strip()
        if prof.heartbeat_metrics_file is not None:
            heartbeat_metrics_file = str(prof.heartbeat_metrics_file).strip()
        if prof.heartbeat_interval_seconds is not None:
            heartbeat_interval_seconds = float(prof.heartbeat_interval_seconds)
        if prof.default_recipe is not None:
            default_recipe = str(prof.default_recipe).strip()
        if prof.hook_pre_run is not None:
            hook_pre_run = str(prof.hook_pre_run).strip()
        if prof.hook_post_run is not None:
            hook_post_run = str(prof.hook_post_run).strip()
        if prof.hook_on_error is not None:
            hook_on_error = str(prof.hook_on_error).strip()
        if prof.hook_timeout_seconds is not None:
            hook_timeout_seconds = float(prof.hook_timeout_seconds)

    # Environment overrides
    if os.environ.get("ARCTIS_GHOST_API_BASE_URL"):
        api_base_url = os.environ["ARCTIS_GHOST_API_BASE_URL"].strip()
    if os.environ.get("ARCTIS_GHOST_WORKFLOW_ID"):
        workflow_id = os.environ["ARCTIS_GHOST_WORKFLOW_ID"].strip()
    if os.environ.get("ARCTIS_API_KEY") is not None:
        api_key = os.environ.get("ARCTIS_API_KEY", "").strip()

    mr = _parse_positive_int(
        os.environ.get("ARCTIS_GHOST_MAX_RETRIES_429"),
        env_name="ARCTIS_GHOST_MAX_RETRIES_429",
    )
    if mr is not None:
        max_retries_429 = mr

    idem = _parse_bool(
        os.environ.get("ARCTIS_GHOST_IDEMPOTENCY"),
        env_name="ARCTIS_GHOST_IDEMPOTENCY",
    )
    if idem is not None:
        generate_idempotency_key = idem

    if os.environ.get("ARCTIS_GHOST_OUTGOING_ROOT", "").strip():
        outgoing_root = os.environ["ARCTIS_GHOST_OUTGOING_ROOT"].strip()
    st_en = _parse_bool(
        os.environ.get("ARCTIS_GHOST_STATE_ENABLED"),
        env_name="ARCTIS_GHOST_STATE_ENABLED",
    )
    if st_en is not None:
        state_enabled = st_en
    if os.environ.get("ARCTIS_GHOST_STATE_DIR", "").strip():
        state_dir = os.environ["ARCTIS_GHOST_STATE_DIR"].strip()

    if os.environ.get("ARCTIS_GHOST_ENVELOPE_AUDITED_BY", "").strip():
        envelope_audited_by = os.environ["ARCTIS_GHOST_ENVELOPE_AUDITED_BY"].strip()
    if os.environ.get("ARCTIS_GHOST_ENVELOPE_BRANDING_VERSION", "").strip():
        envelope_branding_version = os.environ["ARCTIS_GHOST_ENVELOPE_BRANDING_VERSION"].strip()
    if os.environ.get("ARCTIS_GHOST_PLG_STATUS_NOTE", "").strip():
        plg_status_note = os.environ["ARCTIS_GHOST_PLG_STATUS_NOTE"].strip()
    plg_sf = _parse_bool(
        os.environ.get("ARCTIS_GHOST_PLG_STATUS_FILE"),
        env_name="ARCTIS_GHOST_PLG_STATUS_FILE",
    )
    if plg_sf is not None:
        plg_status_file_enabled = plg_sf

    if os.environ.get("ARCTIS_GHOST_HEARTBEAT_URL", "").strip():
        heartbeat_url = os.environ["ARCTIS_GHOST_HEARTBEAT_URL"].strip()
    if os.environ.get("ARCTIS_GHOST_HEARTBEAT_METRICS_FILE", "").strip():
        heartbeat_metrics_file = os.environ["ARCTIS_GHOST_HEARTBEAT_METRICS_FILE"].strip()
    hbi = _parse_float_interval(
        os.environ.get("ARCTIS_GHOST_HEARTBEAT_INTERVAL"),
        env_name="ARCTIS_GHOST_HEARTBEAT_INTERVAL",
    )
    if hbi is not None:
        heartbeat_interval_seconds = hbi

    if os.environ.get("ARCTIS_GHOST_DEFAULT_RECIPE", "").strip():
        default_recipe = os.environ["ARCTIS_GHOST_DEFAULT_RECIPE"].strip()

    if os.environ.get("ARCTIS_GHOST_HOOK_PRE_RUN", "").strip():
        hook_pre_run = os.environ["ARCTIS_GHOST_HOOK_PRE_RUN"].strip()
    if os.environ.get("ARCTIS_GHOST_HOOK_POST_RUN", "").strip():
        hook_post_run = os.environ["ARCTIS_GHOST_HOOK_POST_RUN"].strip()
    if os.environ.get("ARCTIS_GHOST_HOOK_ON_ERROR", "").strip():
        hook_on_error = os.environ["ARCTIS_GHOST_HOOK_ON_ERROR"].strip()
    hto = _parse_float_interval(
        os.environ.get("ARCTIS_GHOST_HOOK_TIMEOUT"),
        env_name="ARCTIS_GHOST_HOOK_TIMEOUT",
    )
    if hto is not None:
        if hto < 0.5 or hto > 600.0:
            raise GhostConfigError("ARCTIS_GHOST_HOOK_TIMEOUT must be between 0.5 and 600")
        hook_timeout_seconds = hto

    api_base_url = api_base_url.rstrip("/")
    return GhostConfig(
        api_base_url=api_base_url,
        workflow_id=workflow_id,
        api_key=api_key,
        profile=profile_name,
        max_retries_429=max_retries_429,
        generate_idempotency_key=generate_idempotency_key,
        outgoing_root=outgoing_root,
        state_enabled=state_enabled,
        state_dir=state_dir,
        envelope_audited_by=envelope_audited_by,
        envelope_branding_version=envelope_branding_version,
        plg_status_note=plg_status_note,
        plg_status_file_enabled=plg_status_file_enabled,
        heartbeat_url=heartbeat_url,
        heartbeat_metrics_file=heartbeat_metrics_file,
        heartbeat_interval_seconds=heartbeat_interval_seconds,
        default_recipe=default_recipe,
        hook_pre_run=hook_pre_run,
        hook_post_run=hook_post_run,
        hook_on_error=hook_on_error,
        hook_timeout_seconds=hook_timeout_seconds,
    )
