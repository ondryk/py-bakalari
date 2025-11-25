"""Simple logging configuration helper for the package."""
from __future__ import annotations

import logging
from typing import Optional


def configure_logging(level: Optional[str] = None) -> None:
    """Configure root logging for simple CLI usage.

    level may be a string like 'INFO' or 'DEBUG'. If not provided, defaults to INFO.
    """
    if isinstance(level, str):
        lvl = getattr(logging, level.upper(), logging.INFO)
    else:
        # default
        lvl = logging.INFO
    handler = logging.StreamHandler()
    fmt = "%(asctime)s %(levelname)s %(name)s: %(message)s"
    handler.setFormatter(logging.Formatter(fmt))
    root = logging.getLogger()
    root.setLevel(lvl)
    # Remove existing handlers to avoid duplicate logs in interactive runs
    for h in list(root.handlers):
        root.removeHandler(h)
    root.addHandler(handler)
