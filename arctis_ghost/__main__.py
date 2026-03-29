"""Allow ``python -m arctis_ghost`` when ``ghost`` is not on PATH."""

from arctis_ghost.cli import main

raise SystemExit(main())
