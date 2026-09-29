"""Structured-ish logging shared by the pipeline, the API and the scheduler."""
from __future__ import annotations

import logging
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager

_CONFIGURED = False


def setup_logging(level: str = "INFO") -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)-7s | %(name)s | %(message)s", "%H:%M:%S")
    )
    root = logging.getLogger("gridalpha")
    root.setLevel(level)
    root.addHandler(handler)
    root.propagate = False
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    setup_logging()
    return logging.getLogger(f"gridalpha.{name}")


@contextmanager
def timed(logger: logging.Logger, label: str, sink: dict | None = None) -> Iterator[None]:
    """Log wall-clock time of a block; optionally store it in `sink[label]`."""
    t0 = time.perf_counter()
    yield
    dt = time.perf_counter() - t0
    if sink is not None:
        sink[label] = round(dt, 3)
    logger.info("%s done in %.2fs", label, dt)
