"""Freemium / PLG — **local** copy only.

Quotas, budgets, and entitlements are enforced **on the Arctis API**. Ghost may surface
hints in ``__STATUS.txt`` or in ``envelope.json`` ``branding`` for human readability only.
"""

from __future__ import annotations


def status_file_lines(*, run_id: str, user_note: str = "") -> list[str]:
    """
    Build UTF-8 lines for ``outgoing_root/__STATUS.txt`` after ``ghost pull-artifacts``.

    No license or entitlement is implied; servers remain authoritative.
    """
    lines = [
        "Arctis Ghost — local status",
        (
            "API-side limits (quota, budget, scopes) apply on the server; "
            "this file is not enforcement."
        ),
        f"last_artifact_run_id: {run_id}",
    ]
    note = user_note.strip()
    if note:
        lines.append(f"note: {note}")
    return lines
