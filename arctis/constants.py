"""Well-known identifiers shared across control plane and migrations."""

from __future__ import annotations

import uuid

# Fallback owner / executor when legacy data or non-user API keys have no explicit user.
SYSTEM_USER_ID: uuid.UUID = uuid.UUID("00000000-0000-0000-0000-000000000001")
