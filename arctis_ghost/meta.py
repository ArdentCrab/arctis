"""P13: read-only Ghost client introspection (Epic K light, §15.12–15.15).

No engine imports; no extra HTTP. Safe for logs (no API key material).
"""

from __future__ import annotations

import platform
import sys
from importlib.metadata import PackageNotFoundError, version

from arctis_ghost.config import GhostConfig


def _distribution_version(name: str = "arctis") -> str | None:
    try:
        return version(name)
    except PackageNotFoundError:
        return None


def ghost_meta_dict(cfg: GhostConfig) -> dict[str, object]:
    """
    Structured metadata: resolved config (non-secret), runtime, and roadmap labels.

    ``api_key`` is never included; only whether one is configured.
    """
    return {
        "schema_version": "1.0",
        "kind": "ghost_meta",
        "label": "Pilot — Epic K (§15.12–15.15); not a production multi-region router",
        "package": {
            "distribution": "arctis",
            "version": _distribution_version("arctis"),
        },
        "runtime": {
            "python": sys.version.split()[0],
            "platform": platform.system(),
        },
        "config": {
            "profile": cfg.profile,
            "api_base_url": cfg.api_base_url,
            "workflow_id": cfg.workflow_id,
            "outgoing_root": cfg.outgoing_root,
            "state_enabled": cfg.state_enabled,
            "state_dir": cfg.state_dir,
            "credentials_configured": bool(str(cfg.api_key).strip()),
        },
        "capabilities": {
            "predict": {
                "status": "roadmap",
                "detail": "Not implemented in Ghost CLI; backend-only when available.",
            },
            "replay": {
                "status": "roadmap",
                "detail": "Not implemented in Ghost CLI.",
            },
            "multi_region": {
                "status": "pilot",
                "detail": (
                    "Single api_base_url from ghost.yaml / env; no client-side failover."
                ),
            },
            "lifecycle_hooks": {
                "status": "pilot",
                "detail": (
                    "Optional pre_run/post_run/on_error subprocess hooks (P14); "
                    "not a policy engine."
                ),
            },
        },
    }
