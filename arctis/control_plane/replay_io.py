"""Persisted I/O for snapshot replay: clone source run rows for audit parity."""

from __future__ import annotations

import copy
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from arctis.db.models import RunInput, RunOutput
from arctis.engine.runtime import _persist_run_input_row, _persist_run_output_rows


def copy_run_io_for_replay(
    db: Session,
    source_run_id: uuid.UUID,
    dest_run_id: uuid.UUID,
    *,
    fallback_input: dict[str, Any],
    fallback_output: dict[str, Any],
) -> None:
    """
    When both source :class:`~arctis.db.models.RunInput` and ``RunOutput`` exist, copy
    them verbatim onto ``dest_run_id``. Otherwise seed I/O using the same persistence
    helpers as live :meth:`~arctis.engine.runtime.Engine.run` (legacy runs without rows).
    """
    src_in = db.scalars(select(RunInput).where(RunInput.run_id == source_run_id)).first()
    src_out = db.scalars(select(RunOutput).where(RunOutput.run_id == source_run_id)).first()

    if src_in is not None and src_out is not None:
        db.add(
            RunInput(
                id=uuid.uuid4(),
                run_id=dest_run_id,
                raw_input=src_in.raw_input,
                sanitized_input=src_in.sanitized_input,
                effective_input=src_in.effective_input,
            )
        )
        mo = src_out.model_output
        db.add(
            RunOutput(
                id=uuid.uuid4(),
                run_id=dest_run_id,
                raw_output=src_out.raw_output,
                sanitized_output=src_out.sanitized_output,
                model_output=copy.deepcopy(mo) if mo is not None else None,
            )
        )
    else:
        _persist_run_input_row(db, dest_run_id, fallback_input)
        _persist_run_output_rows(
            db,
            dest_run_id,
            copy.deepcopy(fallback_input),
            dict(fallback_output),
        )
    db.flush()
